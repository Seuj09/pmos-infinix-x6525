// SPDX-License-Identifier: GPL-2.0-only
/*
 * Read a physical memory range from a loadable module (System RAM is blocked
 * by CONFIG_STRICT_DEVMEM, so /dev/mem cannot see the modem's shared memory).
 *
 * Two hashes are taken wait_ms apart so a range can be watched while the
 * modem/CP is started from another shell.  The first bytes are dumped too.
 */
#include <linux/delay.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/string.h>

static unsigned long addr = 0x87800000;
module_param(addr, ulong, 0444);
MODULE_PARM_DESC(addr, "physical address to peek");

static unsigned int size = 0x800000;
module_param(size, uint, 0444);
MODULE_PARM_DESC(size, "number of bytes to peek");

static unsigned int wait_ms = 2000;
module_param(wait_ms, uint, 0444);
MODULE_PARM_DESC(wait_ms, "delay between the two hashes");

static u64 hash_mem(const void *p, unsigned int len)
{
	const u8 *b = p;
	u64 h = 0xcbf29ce484222325ULL;
	unsigned int i;

	for (i = 0; i < len; i++) {
		h ^= b[i];
		h *= 0x100000001b3ULL;
	}
	return h;
}

static int __init mempeek_init(void)
{
	void *p;
	u64 h1, h2;
	int i;

	if (!size || size > 64 * 1024 * 1024)
		return -EINVAL;

	p = memremap(addr, size, MEMREMAP_WB);
	if (!p) {
		pr_err("mempeek: memremap(%lx, %x) failed\n", addr, size);
		return -ENOMEM;
	}

	h1 = hash_mem(p, size);
	msleep(wait_ms);
	h2 = hash_mem(p, size);
	pr_info("mempeek: %lx+%x hash1=%016llx hash2=%016llx %s\n",
		addr, size, h1, h2, h1 == h2 ? "same" : "CHANGED");
	pr_info("mempeek: first %u bytes:", min(size, 64u));
	for (i = 0; i < min(size, 64u); i++)
		pr_cont(" %02x", ((u8 *)p)[i]);
	pr_cont("\n");

	memunmap(p);
	return 0;
}

static void __exit mempeek_exit(void)
{
}

module_init(mempeek_init);
module_exit(mempeek_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Peek at physical memory from a module");
