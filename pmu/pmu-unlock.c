// SPDX-License-Identifier: GPL-2.0-only
/*
 * Clear the Unisoc PMU DSP-reset bits for the modem CP on the X6525.
 *
 * The stock loader exposes the modem's syscon5 ("dspreset", pmu_apb + 0xb88,
 * mask 0x18) but its start sequence does not touch it. The bits are still
 * asserted after the mainline sprd_modem start, which may keep the CP's DSPs
 * in reset before it reaches its SIPC loop.
 */
#include <linux/init.h>
#include <linux/mfd/syscon.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regmap.h>

#define PMU_DSPRESET_REG	0xb88
#define PMU_DSPRESET_MASK	0x18

static int __init pmu_unlock_init(void)
{
	struct device_node *np;
	struct regmap *pmu;
	unsigned int val;

	np = of_find_node_by_path("/soc/syscon@64020000");
	if (!np) {
		pr_err("pmu_unlock: PMU syscon node not found\n");
		return -ENODEV;
	}
	pmu = syscon_node_to_regmap(np);
	of_node_put(np);
	if (IS_ERR(pmu)) {
		pr_err("pmu_unlock: no PMU regmap: %ld\n", PTR_ERR(pmu));
		return PTR_ERR(pmu);
	}

	regmap_read(pmu, PMU_DSPRESET_REG, &val);
	pr_info("pmu_unlock: dspreset before = 0x%08x\n", val);
	regmap_update_bits(pmu, PMU_DSPRESET_REG, PMU_DSPRESET_MASK, 0);
	regmap_read(pmu, PMU_DSPRESET_REG, &val);
	pr_info("pmu_unlock: dspreset after = 0x%08x\n", val);

	return 0;
}

static void __exit pmu_unlock_exit(void)
{
}

module_init(pmu_unlock_init);
module_exit(pmu_unlock_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Clear the X6525 modem DSP reset bits");
