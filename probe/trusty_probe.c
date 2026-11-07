// SPDX-License-Identifier: GPL-2.0-only
/*
 * Probe the Unisoc secure monitor's Trusty SMC interface.
 *
 * The X6525 stock boot chain starts TrustOS and its modem loader asks the
 * kernelbootcp trustlet to unlock DDR for the CP. Mainline has no Trusty
 * driver, so before porting one this module only checks whether the SMC
 * service is still reachable after U-Boot and Linux have taken over.
 */
#include <linux/arm-smccc.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>

#define SMC_ENTITY_SECURE_MONITOR	60

#define SMC_FASTCALL_NR(entity, fn) \
	((1U << 31) | (((entity) & 0x3f) << 24) | ((fn) & 0xffff))

#define SMC_FC_GET_VERSION_STR	SMC_FASTCALL_NR(SMC_ENTITY_SECURE_MONITOR, 10)
#define SMC_FC_API_VERSION	SMC_FASTCALL_NR(SMC_ENTITY_SECURE_MONITOR, 11)

static int __init trusty_probe_init(void)
{
	struct arm_smccc_res res;

	pr_info("trusty_probe: requesting Trusty API version 3\n");
	arm_smccc_smc(SMC_FC_API_VERSION, 3, 0, 0, 0, 0, 0, 0, &res);
	pr_info("trusty_probe: API_VERSION -> a0=0x%lx a1=0x%lx a2=0x%lx a3=0x%lx\n",
		res.a0, res.a1, res.a2, res.a3);

	arm_smccc_smc(SMC_FC_GET_VERSION_STR, 0, 0, 0, 0, 0, 0, 0, &res);
	pr_info("trusty_probe: VERSION_STR -> a0=0x%lx a1=0x%lx a2=0x%lx a3=0x%lx\n",
		res.a0, res.a1, res.a2, res.a3);

	return 0;
}

static void __exit trusty_probe_exit(void)
{
	pr_info("trusty_probe: unloaded\n");
}

module_init(trusty_probe_init);
module_exit(trusty_probe_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Probe the Unisoc Trusty SMC interface");
