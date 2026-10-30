# Astra v3 calibration source-proof audit — 30 October 2026

**Accepted: 20/20 labels and 20/20 source proofs.** Reused development: 12/12; fresh held-out response checks: 8/8. All twenty requests finished before this separate audit.

Actual response window: 2026-10-30T21:01:47.144087+00:00 to 2026-10-30T21:09:15.637071+00:00. Audit time: 2026-10-30T21:14:44.150332+00:00.

Reported usage: 26,732 input tokens (26,672 cache-write; 0 cache-hit), 23,997 output tokens including 11,266 reasoning tokens. Estimated cost: $1.5338; the provider billing dashboard is authoritative.

The immutable first answers and original acquisition archive are preserved. The exported files, frozen packet bank, request/schema order, profile, source identity and raw-response import provenance all match. Reported model is gpt-6-astra, reasoning effort high, service tier default throughout.

## Citation precision and scope

R17 loop proofs cite the header/body without separately citing visible L6 size_t i. The finite range is supported by the displayed declaration and loop. Audited as visible support, not an exact-reference-line checklist; raw answers unchanged.

D01 and R15 reduced positives correctly use explicit copy count or visible initialization/termination rather than inventing omitted source-array capacity. Incomplete controls reject missing guard, alias or destination bound; they do not infer vulnerability from a source-array size or hypothetical external caller. These are checks of the declared claim-conditioned task, not a program-wide safety proof.

## Per-packet decisions

| Case | View | Expected / observed | Source proof |
|---|---|---|---|
| D01 | complete_U | adequate / adequate | Supported |
| D01 | complete_F | inadequate / inadequate | Supported |
| D01 | reduced_sufficient_U | adequate / adequate | Supported |
| D01 | indistinguishable_incomplete | inadequate / inadequate | Supported |
| D02 | complete_U | adequate / adequate | Supported |
| D02 | complete_F | inadequate / inadequate | Supported |
| D02 | reduced_sufficient_U | adequate / adequate | Supported |
| D02 | indistinguishable_incomplete | inadequate / inadequate | Supported |
| D03 | complete_U | adequate / adequate | Supported |
| D03 | complete_F | inadequate / inadequate | Supported |
| D03 | reduced_sufficient_U | adequate / adequate | Supported |
| D03 | indistinguishable_incomplete | inadequate / inadequate | Supported |
| R15 | complete_U | adequate / adequate | Supported |
| R15 | complete_F | inadequate / inadequate | Supported |
| R15 | reduced_sufficient_U | adequate / adequate | Supported |
| R15 | indistinguishable_incomplete | inadequate / inadequate | Supported |
| R17 | complete_U | adequate / adequate | Supported |
| R17 | complete_F | inadequate / inadequate | Supported |
| R17 | reduced_sufficient_U | adequate / adequate | Supported |
| R17 | indistinguishable_incomplete | inadequate / inadequate | Supported |

## Detailed support

### D01: complete_U

Packet `4b68a139116ee6b9b8bcc9442994f6ec62fbda7081cedd506fb3c346ea475768`. Visible audit citations: L2, L5, L6, L14, L15.

L14 supplies a 10-byte ALLOCA object; L15 passes its address to the int-pointer formal at L2, used as the destination at L6. The requested copy is 10*sizeof(int)=40 bytes under the permitted LP64 assumption; L5 supplies a 40-byte source. The response correctly attributes the overflow to the destination and gives 40-10=30 bytes of excess. No hidden value is supplied.

### D01: complete_F

Packet `11dac1464d3130e3d92c58244c7b81a8a320b0b4d867b129e6c9b855285c28bc`. Visible audit citations: L2, L5, L6, L14, L15.

The selected destination allocation at L14 is 10*sizeof(int)=40 bytes. The L15/L2 binding makes this the L6 destination, and both the source capacity at L5 and explicit copy count are 40 bytes. The response rejects this particular overflow because the write fits exactly, without asserting global safety.

### D01: reduced_sufficient_U

Packet `4a0856e3edd2437e6f8a4ec7b13cc6860d3fcccec840aecd8d9c670086d834b9`. Visible audit citations: L2, L6, L14, L15.

The visible allocation L14 is 10 bytes, the caller/formal binding is L15/L2, and the explicit destination count at L6 is 10*4=40 bytes. The response derives the destination overflow directly from that count; it does not invent the omitted source declaration or use source contents to determine memcpy length. Its stated source-side-validity limitation is appropriate.

### D01: indistinguishable_incomplete

Packet `5a0df3abb0902cf0770a8be1ba8814e80bed7dc47352a0a1573ebf9a3281cb67`. Visible audit citations: L2, L5, L6, L13, L15.

The 40-byte copy count and 40-byte source are visible at L6/L5, but the destination allocation between L13 and L15 is omitted. The response correctly distinguishes the source bound from the missing destination bound. It neither assumes NULL persists through the gap nor reclassifies a possible NULL dereference as the claimed stack overflow.

### D02: complete_U

Packet `f6526d234dd28050582f74da9eb23a955cad6e62f077dbf99d9b0e9eb44ac24b`. Visible audit citations: L2, L3, L7, L8, L13, L15, L30, L33, L34, L36, L43.

L2/L30/L33 establish the 14-byte input buffer; L34/L36 permit the short input 10 followed by newline to become integer 10. L43 binds that value to L3. L7 provides ten ints/40 bytes; the L13 guard admits 10, and L15 writes bytes 40-43 beyond valid bytes 0-39. The response supplies the input witness, guard, object binding and arithmetic rather than relying solely on a missing upper-bound check.

### D02: complete_F

Packet `42d19ed58e1dc7fcd4a42f5d4aaece89e7fc89f9bdb43fe687ea6b6e19af013b`. Visible audit citations: L3, L7, L8, L13, L15, L21, L23, L31, L34, L36, L43.

L7 supplies ten ints/40 bytes and L13 admits only 0<=data<10. The L43/L3 binding carries the parsed entry value to this guard; the L15 store is at most index 9, bytes 36-39. The response correctly rejects the claim using the actual guard and allocation, not the error-message text or a false assumption about input capacity.

### D02: reduced_sufficient_U

Packet `a1ad5b22308c84a3d929dd64ef66b99d00620390871f221ff418dff43d2c8d9b`. Visible audit citations: L2, L3, L7, L13, L15, L30, L33, L34, L36, L43.

The reduced view retains the macro and int type giving a 14-byte input buffer, successful fgets/atoi acquisition of 10, caller/formal binding, 40-byte malloc object, nonnegative-only guard and indexed store. The response gives the supported [40,44) write outside [0,40). Allocation success is permitted; it does not invent an unseen upper-bound check or rely on the omitted diagnostic text.

### D02: indistinguishable_incomplete

Packet `86bbbe383797318565d2183d840defd5204edf4f24687e2745edf3c231289269`. Visible audit citations: L2, L3, L7, L14, L15, L21, L30, L33, L34, L36, L43.

The allocation, input-derived value 10 and caller/formal relation are visible, but the predicate controlling L14-L20 is omitted. The response explicitly makes the overflow arithmetic conditional and explains that a hidden predicate could reject every out-of-range index. It therefore correctly rejects justification of the entry-path flaw instead of inferring an unconditional write from an incomplete view.

### D03: complete_U

Packet `e3b1d29a82d228fbb9141b8afefb1feaaa71cca3a8ba0beb6a94f85a293da7a6`. Visible audit citations: L5, L6, L9, L10, L17, L19, L21.

L5 gives ten A characters and L9 adds the terminating NUL, so strcpy at L10 copies 11 bytes. L17 supplies a 10-byte stack object; L19 selects it and L21/L6 bind it to the destination. The response correctly identifies the one-byte terminator overflow and cites both initializer dependencies and the alias selection.

### D03: complete_F

Packet `0d8ef066c6eae55811decd566b412746fb538ae1ef4e0001ad2174006ccae338`. Visible audit citations: L5, L6, L9, L10, L17, L18, L19, L21.

The same 11-byte source copy is established by L5/L9/L10, but L19 selects buffer_8, whose L18 allocation is 11 bytes. The L21/L6 caller/formal relation makes that the actual destination. The response correctly avoids treating the separate 10-byte buffer_7 allocation as the selected object and rejects only the documented claim.

### D03: reduced_sufficient_U

Packet `652e63294acdcaf29f64cd14c9fe48ff2d73a11f81e7776e2cbd0eaab7a49cbe`. Visible audit citations: L5, L6, L9, L10, L17, L19, L21.

The reduced view retains the source macro, initialized 11-element source, strcpy, 10-byte allocation, alias assignment and caller/formal binding. The response derives 10 characters plus NUL=11 bytes into the selected 10-byte object. No omitted macro, arbitrary source length or unseen alias selection is used.

### D03: indistinguishable_incomplete

Packet `aecc26c35c50926787ec4aded1775430189fc1b7f64083a126be2e44ed7d1e81`. Visible audit citations: L5, L6, L9, L10, L17, L18, L20, L21.

The 11-byte copy and both 10-byte/11-byte allocations are visible, but the assignment selecting the destination is omitted. The response correctly notes that data[0]=NUL changes contents rather than assigning the pointer and that the call alone does not choose either object. The same visible packet is compatible with U and F, so the insufficient-binding rejection is source-supported.

### R15: complete_U

Packet `90522a90d67b57b773b4db4ea5823efc13d2f6b892ce3efe49622e26f55a00ef`. Visible audit citations: L3, L6, L7, L8, L9, L18, L19, L21.

L18/L19 supply the successful 50-byte heap allocation, passed by L21 to the L3 formal and used at L9. L7 fills indices 0-98 with nonzero C and L8 terminates at 99, proving length 99 and a 100-byte strcpy extent. The response establishes 100-50=50 bytes of destination excess from initialization/termination, not source-array capacity alone.

### R15: complete_F

Packet `0a0acdd3b0214877c9dd10c2c4a4875a9e1333ee016ef3ca0a765c8039bac341`. Visible audit citations: L3, L6, L7, L8, L9, L18, L19, L21.

L7/L8 establish a 99-character string plus NUL, so L9 copies 100 bytes. The selected L18 destination allocation is also 100 bytes, with L21/L3 binding. The response correctly rejects the claim because bytes 0-99 fit exactly and does not claim whole-program safety.

### R15: reduced_sufficient_U

Packet `dbf5061f3de756bea8f5868174ab466446075d271e0b22f633ba1be7aeef366b`. Visible audit citations: L3, L7, L8, L9, L18, L21.

The visible memset count and explicit terminator at L7/L8 determine a 99-character string independently of an omitted source-array capacity declaration. L9 therefore specifies a 100-byte strcpy copy. L18/L21/L3 bind the selected 50-byte heap allocation to the destination. This is the declared sufficient account: the response does not infer length from unseen capacity or invent an initializer.

### R15: indistinguishable_incomplete

Packet `0beb3d2594de64e20c07ee94d94d7ee7cc7235b76d8c46d8f6659c1c912180b1`. Visible audit citations: L3, L6, L7, L8, L9, L19, L20, L21.

The 100-byte copy extent and caller/formal binding are supported, but the destination allocation line is absent. The null check and initial empty string at L19/L20 establish neither heap provenance nor capacity. The response correctly identifies that missing object-size premise and does not use the source array bound or an arbitrary external caller to supply it.

### R17: complete_U

Packet `a64f7fd3e4dbee04dfc164a9df717da394f31011a906073bbe45c1232ae5de7e`. Visible audit citations: L3, L6, L7, L8, L9, L10, L12, L23, L24, L25, L26.

L23/L24 provide the successful 50-byte heap object and L26/L3 bind it to data at L12. The visible size_t counter at L6 and L10 loop header support indices 0-99, yielding 100 one-byte writes; the first invalid write is index 50. The response correctly uses the fixed loop count, not string length, and its source-initialization context matches L7-L9. Citation precision note: the response cites the loop header/body rather than separately listing L6; the counter declaration is visible and its claimed loop range is supported without hidden information.

### R17: complete_F

Packet `1d7e2b3a2df835b0214400177ccfb4e7daeede76dfebd3546b21a99fa56c8213`. Visible audit citations: L3, L6, L10, L12, L14, L23, L24, L26.

L23 selects 100 bytes, bound through L26/L3. The visible size_t declaration L6 and header L10 support indices 0-99; both the L12 loop and L14 terminator at index 99 fit. The response correctly rejects the claim from the actual destination bound. As in the other R17 positives, its citations emphasize the header/body rather than the visible counter declaration; this is a citation-granularity note, not an absent or false premise.

### R17: reduced_sufficient_U

Packet `2fc74f8df646f5e1b806a1f59307529d8b8a6f22edf2e35e57e5d4501477d2e0`. Visible audit citations: L3, L6, L10, L12, L23, L26.

The reduced view retains size_t i at L6, the fixed 0<=i<100 loop at L10, the char-pointer destination/store L3/L12, the 50-byte allocation L23 and call L26. These support 100 one-byte destination writes and the first out-of-bounds write at index 50. The response does not invent omitted source contents or derive the count from termination. Its header/body citations omit a separate L6 citation, but the supplying counter declaration remains visible and supports its finite loop-range claim.

### R17: indistinguishable_incomplete

Packet `13469d99ec4bf9699e5c9b43f6bb1cb4ae029abbce81ca90cee97793a1e03b98`. Visible audit citations: L3, L6, L7, L10, L12, L14, L24, L26.

The fixed 100-byte destination range and caller/formal relation are visible; the allocation identifying and sizing that destination is omitted. The source-array size and NULL check cannot establish a smaller heap destination. The response correctly rejects this particular overflow justification while allowing that a destination of at least 100 bytes would fit the shown accesses.

## Interpretation

Small correlated curated instrument screen (12 reused development / 8 held-out response checks), AI-assisted key and audit, no independent human validation or population accuracy; snprintf/strncat-specific calibration remains absent.

Acceptance applies to this frozen assessor profile and instrument. It permits development release once sealed Q/Joern data exist. It does not create Q outputs, establish main adequacy or permit main release before the development audit and assessment freeze.

The next checkpoint is Q-host technical inspection using the accepted v7 Q-input archive. Preserve the existing VM packages and cached weights; obtain the current console IP and running-cost/balance information before starting its paid checkpoint.
