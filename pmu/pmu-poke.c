// SPDX-License-Identifier: GPL-2.0-only
/*
 * PUBCP (modem R5) bring-up helper for the Infinix X6525.
 *
 * The PMU/AON APB status registers ignore direct writes; they are only
 * changed through the set/clear alias windows at +0x1000/+0x2000 (this is
 * what the PMU power-domain driver and the secure monitor use).  The
 * mainline modem driver pokes the status registers directly, so its core
 * reset release never reaches the hardware.  Drive the aliases through the
 * syscon regmaps here and optionally run the stock soc_modem_start()
 * sequence, so the CP can be started from userspace while the driver is
 * being fixed.
 */
#include <linux/delay.h>
#include <linux/init.h>
#include <linux/mfd/syscon.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/of.h>
#include <linux/regmap.h>

#define PMU_PATH "/soc/syscon@64020000"
#define AON_PATH "/soc/syscon@64000000"

/* PUBCP register offsets and masks from the vendor qogirl6 headers */
#define PMU_PD_PUBCP_CFG0	0x330
#define PMU_FORCE_SHUTDOWN	BIT(25)
#define PMU_AUTO_SHUTDOWN	BIT(24)
#define PMU_FORCE_DEEP_SLEEP_CFG0 0x818
#define PMU_PUBCP_FORCE_DEEP_SLEEP BIT(1)
#define PMU_SYS_SOFT_RST0	0xb98
#define PMU_PUBCP_SOFT_RST	BIT(11)
#define PMU_DM_SOFT_RST		0xb88
#define PMU_PUBCP_DSP_RESET	0x18
#define AON_PCP_AON_EB		0x170
#define AON_PCP_AON_EB_MASK	0xffc
#define AON_PCP_SOFT_RST	0x174
#define AON_PUBCP_CR5_CORE_RST	BIT(10)

static bool start;
static bool aon_eb;
static bool dsp_clear;
static bool pulse_only;

module_param(start, bool, 0444);
MODULE_PARM_DESC(start, "Run the stock PUBCP power-on and reset-release sequence");
module_param(aon_eb, bool, 0444);
MODULE_PARM_DESC(aon_eb, "Set the PCP AON clock enable bits (0x170 = 0xffc)");
module_param(dsp_clear, bool, 0444);
MODULE_PARM_DESC(dsp_clear, "Clear the PUBCP DSP reset bits (0xb88 mask 0x18)");
module_param(pulse_only, bool, 0444);
MODULE_PARM_DESC(pulse_only, "Assert and release the resets without changing power bits");

static struct regmap *pmu;
static struct regmap *aon;

static void show(struct regmap *map, const char *tag, unsigned int reg)
{
	unsigned int v = 0;

	regmap_read(map, reg, &v);
	pr_info("pmu_poke: %s[0x%03x] = 0x%08x\n", tag, reg, v);
}

static void poke(struct regmap *map, const char *tag, unsigned int reg,
		 unsigned int mask, bool set)
{
	unsigned int off = reg + (set ? 0x1000 : 0x2000);
	unsigned int v = 0;
	int ret;

	ret = regmap_write(map, off, mask);
	regmap_read(map, reg, &v);
	pr_info("pmu_poke: %s %s 0x%03x (write 0x%x to 0x%03x, ret %d) -> 0x%08x\n",
		set ? "set" : "clear", tag, reg, mask, off, ret, v);
}

static int __init pmu_poke_init(void)
{
	struct device_node *np;
	int ret;

	np = of_find_node_by_path(PMU_PATH);
	if (!np)
		return -ENODEV;
	pmu = syscon_node_to_regmap(np);
	of_node_put(np);
	if (IS_ERR(pmu))
		return PTR_ERR(pmu);

	np = of_find_node_by_path(AON_PATH);
	if (!np)
		return -ENODEV;
	aon = syscon_node_to_regmap(np);
	of_node_put(np);
	if (IS_ERR(aon))
		return PTR_ERR(aon);

	pr_info("pmu_poke: start=%d aon_eb=%d dsp_clear=%d pulse_only=%d\n",
		start, aon_eb, dsp_clear, pulse_only);
	show(pmu, "pmu", PMU_PD_PUBCP_CFG0);
	show(pmu, "pmu", PMU_FORCE_DEEP_SLEEP_CFG0);
	show(pmu, "pmu", PMU_SYS_SOFT_RST0);
	show(pmu, "pmu", PMU_DM_SOFT_RST);
	show(aon, "aon", AON_PCP_SOFT_RST);
	show(aon, "aon", AON_PCP_AON_EB);

	if (dsp_clear)
		poke(pmu, "dspreset", PMU_DM_SOFT_RST,
		     PMU_PUBCP_DSP_RESET, false);

	if (aon_eb)
		poke(aon, "pcp_aon_eb", AON_PCP_AON_EB,
		     AON_PCP_AON_EB_MASK, true);

	if (start || pulse_only) {
		/* LK's pubcp_boot(): assert the resets first */
		poke(pmu, "sysreset", PMU_SYS_SOFT_RST0,
		     PMU_PUBCP_SOFT_RST, true);
		poke(aon, "corereset", AON_PCP_SOFT_RST,
		     AON_PUBCP_CR5_CORE_RST, true);

		if (start) {
			/* power on: force shutdown, auto shutdown, deep sleep */
			poke(pmu, "shutdown", PMU_PD_PUBCP_CFG0,
			     PMU_FORCE_SHUTDOWN | PMU_AUTO_SHUTDOWN, false);
			poke(pmu, "deepsleep", PMU_FORCE_DEEP_SLEEP_CFG0,
			     PMU_PUBCP_FORCE_DEEP_SLEEP, false);
		}

		msleep(50);

		/* release the subsystem reset, then the core reset */
		poke(pmu, "sysreset", PMU_SYS_SOFT_RST0,
		     PMU_PUBCP_SOFT_RST, false);
		poke(aon, "corereset", AON_PCP_SOFT_RST,
		     AON_PUBCP_CR5_CORE_RST, false);
		msleep(50);

		show(pmu, "pmu", PMU_PD_PUBCP_CFG0);
		show(pmu, "pmu", PMU_SYS_SOFT_RST0);
		show(aon, "aon", AON_PCP_SOFT_RST);
	}

	return 0;
}

static void __exit pmu_poke_exit(void)
{
}

module_init(pmu_poke_init);
module_exit(pmu_poke_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("X6525 PUBCP/AON PMU alias poke and modem start helper");
