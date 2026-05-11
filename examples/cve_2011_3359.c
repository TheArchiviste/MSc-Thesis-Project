/*
 * Simplified illustration of CVE-2011-3359 (Linux kernel libertas wireless
 * driver, missing length check on a network frame copy).
 *
 * The vulnerable function copies attacker-controlled `len` bytes into a
 * fixed-size stack buffer with no upper bound. A long taint chain runs from
 * `nla_get_u32` (the source) through the `len` variable to `memcpy` (the
 * sink), and that's exactly what a CPGQL execution-path query is supposed
 * to surface. Used as the smoke-test input in scripts/run_pipeline.py.
 */

#include <string.h>

struct nlattr;
struct cmd_ds_802_11_beacon_set { unsigned char beacon[256]; };

extern unsigned int nla_get_u32(struct nlattr *nla);
extern void *nla_data(struct nlattr *nla);

void process_beacon(struct nlattr *attr, struct cmd_ds_802_11_beacon_set *cmd)
{
    unsigned int len;
    void *src;

    len = nla_get_u32(attr);          /* attacker-controlled */
    src = nla_data(attr);

    /* BUG: no `if (len > sizeof(cmd->beacon)) return;` here. */
    memcpy(cmd->beacon, src, len);    /* CWE-119 buffer overflow sink */
}

int main(void) { return 0; }
