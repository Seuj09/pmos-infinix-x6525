// SPDX-License-Identifier: GPL-2.0-only
/*
 * PUBCP (modem R5) bring-up helper for the Infinix X6525.
 *
 * The PMU/AON APB register blocks can be accessed in two ways: direct
 * read-modify-write of the status register (what the stock modem loader
 * does) or through the set/clear alias windows at +0x1000/+0x2000 (what
 * mainline's PMU power-domain driver does for a few registers).  This
 * module can exercise both and run the stock soc_modem_start() sequence,
 * so the CP can be started from userspace while the driver is debugged.
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
#define AON_REG_PROT		0x7c
#define AON_PCP_AON_EB		0x170
#define AON_PCP_AON_EB_MASK	0xffc
#define AON_PCP_SOFT_RST	0x174
#define AON_PUBCP_CR5_CORE_RST	BIT(10)

static bool start;
static bool aon_eb;
static bool dsp_clear;
static bool pulse_only;
static bool direct_test;
static bool unlock_aon;
static bool direct_start;
static unsigned int aon_key = 0x9620;

module_param(start, bool, 0444);
MODULE_PARM_DESC(start, "Run the PUBCP power-on and reset-release sequence");
module_param(aon_eb, bool, 0444);
MODULE_PARM_DESC(aon_eb, "Set the PCP AON clock enable bits (0x170 = 0xffc)");
module_param(dsp_clear, bool, 0444);
MODULE_PARM_DESC(dsp_clear, "Clear the PUBCP DSP reset bits (0xb88 mask 0x18)");
module_param(pulse_only, bool, 0444);
MODULE_PARM_DESC(pulse_only, "Assert and release the resets without changing power bits");
module_param(direct_test, bool, 0444);
MODULE_PARM_DESC(direct_test, "Exercise direct status writes and alias writes on the reset registers");
module_param(unlock_aon, bool, 0444);
MODULE_PARM_DESC(unlock_aon, "Write the AON register-protection key before the direct test");
module_param(direct_start, bool, 0444);
MODULE_PARM_DESC(direct_start, "Use direct status writes instead of aliases for start");
module_param(aon_key, uint, 0444);
MODULE_PARM_DESC(aon_key, "Value written to AON_REG_PROT (default 0x9620)");

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
	pr_info("pmu_poke: alias %s %s 0x%03x (w 0x%x to 0x%03x, ret %d) -> 0x%08x\n",
		set ? "set" : "clear", tag, reg, mask, off, ret, v);
}

static void direct(struct regmap *map, const char *tag, unsigned int reg,
		   unsigned int mask, bool set, unsigned int extra_set)
{
	unsigned int v = 0, val;
	int ret;

	regmap_read(map, reg, &v);
	val = set ? (v | mask | extra_set) : (v & ~mask);
	ret = regmap_write(map, reg, val);
	regmap_read(map, reg, &v);
	pr_info("pmu_poke: direct %s %s 0x%03x (ret %d) -> 0x%08x\n",
		set ? "set" : "clear", tag, reg, ret, v);
}

static int __init pmu_poke_init(void)
{
	struct device_node *np;

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

	pr_info("pmu_poke: start=%d aon_eb=%d dsp_clear=%d pulse_only=%d direct_test=%d unlock_aon=%d direct_start=%d aon_key=0x%x\n",
		start, aon_eb, dsp_clear, pulse_only, direct_test,
		unlock_aon, direct_start, aon_key);
	show(pmu, "pmu", PMU_PD_PUBCP_CFG0);
	show(pmu, "pmu", PMU_FORCE_DEEP_SLEEP_CFG0);
	show(pmu, "pmu", PMU_SYS_SOFT_RST0);
	show(pmu, "pmu", PMU_DM_SOFT_RST);
	show(aon, "aon", AON_REG_PROT);
	show(aon, "aon", AON_PCP_SOFT_RST);
	show(aon, "aon", AON_PCP_AON_EB);

	if (unlock_aon) {
		unsigned int v = 0;
		int ret = regmap_write(aon, AON_REG_PROT, aon_key);
		regmap_read(aon, AON_REG_PROT, &v);
		pr_info("pmu_poke: unlock aon_reg_prot (ret %d) -> 0x%08x\n",
			ret, v);
	}

	if (direct_test) {
		direct(pmu, "sysreset", PMU_SYS_SOFT_RST0,
		       PMU_PUBCP_SOFT_RST, true, 0);
		direct(pmu, "sysreset", PMU_SYS_SOFT_RST0,
		       PMU_PUBCP_SOFT_RST, false, 0);
		direct(pmu, "deepsleep", PMU_FORCE_DEEP_SLEEP_CFG0,
		       PMU_PUBCP_FORCE_DEEP_SLEEP, true, 0);
		direct(pmu, "deepsleep", PMU_FORCE_DEEP_SLEEP_CFG0,
		       PMU_PUBCP_FORCE_DEEP_SLEEP, false, 0);
		direct(aon, "corereset", AON_PCP_SOFT_RST,
		       AON_PUBCP_CR5_CORE_RST, true, 0);
		direct(aon, "corereset", AON_PCP_SOFT_RST,
		       AON_PUBCP_CR5_CORE_RST, false, 0);
		direct(pmu, "dspreset", PMU_DM_SOFT_RST,
		       PMU_PUBCP_DSP_RESET, false, 0);
		direct(aon, "pcp_aon_eb", AON_PCP_AON_EB,
		       0, true, AON_PCP_AON_EB_MASK);
		/* now the alias path, for comparison */
		poke(pmu, "sysreset", PMU_SYS_SOFT_RST0,
		     PMU_PUBCP_SOFT_RST, true);
		poke(pmu, "sysreset", PMU_SYS_SOFT_RST0,
		     PMU_PUBCP_SOFT_RST, false);
		poke(aon, "corereset", AON_PCP_SOFT_RST,
		     AON_PUBCP_CR5_CORE_RST, true);
		poke(aon, "corereset", AON_PCP_SOFT_RST,
		     AON_PUBCP_CR5_CORE_RST, false);
	}

	if (dsp_clear)
		poke(pmu, "dspreset", PMU_DM_SOFT_RST,
		     PMU_PUBCP_DSP_RESET, false);

	if (aon_eb)
		poke(aon, "pcp_aon_eb", AON_PCP_AON_EB,
		     AON_PCP_AON_EB_MASK, true);

	if (start || pulse_only) {
		if (direct_start) {
			/* stock modem_loader modem_reg_ctrl(): direct RMW */
			direct(pmu, "sysreset", PMU_SYS_SOFT_RST0,
			       PMU_PUBCP_SOFT_RST, true, 0);
			direct(aon, "corereset", AON_PCP_SOFT_RST,
			       AON_PUBCP_CR5_CORE_RST, true, 0);
			if (start) {
				direct(pmu, "shutdown", PMU_PD_PUBCP_CFG0,
				       PMU_FORCE_SHUTDOWN | PMU_AUTO_SHUTDOWN,
				       false, 0);
				direct(pmu, "deepsleep",
				       PMU_FORCE_DEEP_SLEEP_CFG0,
				       PMU_PUBCP_FORCE_DEEP_SLEEP, false, 0);
			}
			msleep(50);
			direct(pmu, "sysreset", PMU_SYS_SOFT_RST0,
			       PMU_PUBCP_SOFT_RST, false, 0);
			direct(aon, "corereset", AON_PCP_SOFT_RST,
			       AON_PUBCP_CR5_CORE_RST, false, 0);
		} else {
			poke(pmu, "sysreset", PMU_SYS_SOFT_RST0,
			     PMU_PUBCP_SOFT_RST, true);
			poke(aon, "corereset", AON_PCP_SOFT_RST,
			     AON_PUBCP_CR5_CORE_RST, true);
			if (start) {
				poke(pmu, "shutdown", PMU_PD_PUBCP_CFG0,
				     PMU_FORCE_SHUTDOWN | PMU_AUTO_SHUTDOWN,
				     false);
				poke(pmu, "deepsleep",
				     PMU_FORCE_DEEP_SLEEP_CFG0,
				     PMU_PUBCP_FORCE_DEEP_SLEEP, false);
			}
			msleep(50);
			poke(pmu, "sysreset", PMU_SYS_SOFT_RST0,
			     PMU_PUBCP_SOFT_RST, false);
			poke(aon, "corereset", AON_PCP_SOFT_RST,
			     AON_PUBCP_CR5_CORE_RST, false);
		}
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
MODULE_DESCRIPTION("X6525 PUBCP/AON PMU register access and modem start helper");
