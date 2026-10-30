# Source-grounded mechanism references

Prepared before Q/Joern inference. AI-assisted source reasoning is supported by pinned Juliet sources, exact maps and finite witnesses; it is not independent human annotation or an excerpt-adequacy result.

Each fact is separate from the relationships that must be justified. A visible fact line is descriptive evidence, not proof of sufficiency. Source-only mechanism and repair explanations must never enter the stateless grader request.

## D01 — development, juliet-buffer-CWE131-copy

The selected destination has 10 bytes. The operation requests ten int elements, a 40-byte access range on LP64.

Repair: The repaired allocation reserves 10*sizeof(int), or 40 bytes.

Actual overflowing object: **stack**. Upstream family: `CWE121-CWE131-copy`.
[Prepared U](generated/D01_U.c) · [Fixed F](generated/D01_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__CWE131_memcpy_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 14 | The receiving allocation reserves ten bytes, not ten int elements. |
| extent / extent | 6 | Ten int elements require 40 bytes; a first-invalid-store account is also acceptable. |
| access / sink | 6 | The operation writes through the selected destination pointer. |
| read_object / context | 5 | The read operand has ten int elements; its contents do not determine the copy count. |
| caller_argument / context | 15 | The selected entry supplies this actual argument. |
| callee_parameter / context | 2 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The selected destination has 10 bytes. The operation requests ten int elements, a 40-byte access range on LP64. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |

## D02 — development, juliet-buffer-CWE129

A ten-int heap object has valid indices 0 through 9. The input can be 11; the nonnegative-only guard admits it and buffer[data] writes outside the object.

Repair: The repaired guard additionally requires data < 10.

Actual overflowing object: **heap**. Upstream family: `CWE122-c-CWE129`.
[Prepared U](generated/D02_U.c) · [Fixed F](generated/D02_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s06/CWE122_Heap_Based_Buffer_Overflow__c_CWE129_fgets_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 7 | Ten int elements: 40 bytes on LP64. |
| input_acquisition / context | 34 | Input is obtained from stdin; a decimal value such as 11 is possible. |
| input_bound_definition / context | 2 | The input bound is 3*sizeof(the entry data variable)+2; its definition cannot be invented when omitted. |
| entry_index_type / context | 30 | The entry variable has int type; with the visible size macro the input buffer admits a two-digit value such as 11. |
| input_buffer / context | 33 | The input object is declared with the visible CHAR_ARRAY_SIZE bound. |
| extent / extent | 36 | The converted input supplies the index; it is not a constant derived from the witness label. |
| guard / guard | 13 | This guard has no upper-bound restriction. |
| access / sink | 15 | The converted scalar is used as the index. |
| caller_argument / context | 43 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | A ten-int heap object has valid indices 0 through 9. The input can be 11; the nonnegative-only guard admits it and buffer[data] writes outside the object. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the index scalar; the receiving buffer is allocated locally. |
| guard_context | The selected input can exceed the object bound while satisfying the visible guard. |

## D03 — development, juliet-buffer-CWE193-copy

The source contains ten characters and a terminating NUL. The copy includes eleven bytes, while the selected destination has ten bytes.

Repair: The repaired caller selects the eleven-byte object.

Actual overflowing object: **stack**. Upstream family: `CWE121-CWE193-copy`.
[Prepared U](generated/D03_U.c) · [Fixed F](generated/D03_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__CWE193_char_alloca_cpy_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 17 | The selected receiving object has ten bytes. |
| string_definition / context | 5 | The macro supplies ten non-NUL characters; it cannot be inferred when omitted. |
| source_initialization / extent | 9 | The source array is initialized with SRC_STRING. |
| extent / extent | 10 | strcpy includes the NUL; the loop variant explicitly includes sourceLen + 1. |
| access / sink | 10 | The copy writes through the caller-selected pointer. |
| caller_argument / context | 21 | The selected entry supplies this actual argument. |
| callee_parameter / context | 6 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |
| alias_selection / context | 19 | The assignment identifies which allocated object is actually passed. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The source contains ten characters and a terminating NUL. The copy includes eleven bytes, while the selected destination has ten bytes. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |

## R02 — main, juliet-buffer-CWE805-ncat

The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity.

Repair: The repaired caller selects or allocates a 100-byte destination.

Actual overflowing object: **stack**. Upstream family: `CWE121-CWE805-ncat`.
[Prepared U](generated/R02_U.c) · [Fixed F](generated/R02_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s03/CWE121_Stack_Based_Buffer_Overflow__CWE805_char_alloca_ncat_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 16 | The receiving object has fifty bytes. |
| access / sink | 9 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 7 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 8 | The explicit termination establishes the documented source length. |
| extent / extent | 9 | The count bound and/or string operation determines the access range together with the source facts. |
| destination_initialization / context | 19 | The destination initially denotes the empty string. |
| caller_argument / context | 20 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |
| alias_selection / context | 18 | The assignment identifies which allocated object is actually passed. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |

## R03 — main, juliet-buffer-CWE806-loop

The receiving object has 50 bytes; the documented count and source facts imply a requested 99-byte access range, exceeding its capacity.

Repair: The repaired caller uses a shorter source.

Actual overflowing object: **stack**. Upstream family: `CWE122-c-CWE806-loop`.
[Prepared U](generated/R03_U.c) · [Fixed F](generated/R03_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s09/CWE122_Heap_Based_Buffer_Overflow__c_CWE806_char_loop_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 6 | The receiving object has fifty bytes. |
| access / sink | 11 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 23 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 24 | The explicit termination establishes the documented source length. |
| extent / extent | 8, 9 | The access extent depends on the caller-supplied source length and operation semantics. |
| source_allocation / context | 21 | This allocation supplies the read operand, not the local overflowing destination. |
| loop_index_type / context | 7 | The counter declaration supplies the type needed to justify its loop range; do not assume an omitted counter cannot wrap or saturate early. |
| caller_argument / context | 25 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 99-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the source object whose length drives the local destination write. |

## R04 — main, juliet-buffer-src-copy

The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity.

Repair: The repaired caller uses a shorter source.

Actual overflowing object: **stack**. Upstream family: `CWE121-src-copy`.
[Prepared U](generated/R04_U.c) · [Fixed F](generated/R04_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s08/CWE121_Stack_Based_Buffer_Overflow__src_char_alloca_cpy_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 6 | The receiving object has fifty bytes. |
| access / sink | 7 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 16 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 17 | The explicit termination establishes the documented source length. |
| extent / extent | 7 | The access extent depends on the caller-supplied source length and operation semantics. |
| source_allocation / context | 14 | This allocation supplies the read operand, not the local overflowing destination. |
| caller_argument / context | 18 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |
| alias_selection / context | 15 | The assignment identifies which allocated object is actually passed. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the source object whose length drives the local destination write. |

## R05 — main, juliet-buffer-CWE806-copy

The receiving object has 50 bytes; the documented count and source facts imply a requested 99-byte access range, exceeding its capacity.

Repair: The repaired caller uses a shorter source.

Actual overflowing object: **stack**. Upstream family: `CWE122-c-CWE806-copy`.
[Prepared U](generated/R05_U.c) · [Fixed F](generated/R05_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s09/CWE122_Heap_Based_Buffer_Overflow__c_CWE806_char_memcpy_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 6 | The receiving object has fifty bytes. |
| access / sink | 7 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 18 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 19 | The explicit termination establishes the documented source length. |
| extent / extent | 7 | The access extent depends on the caller-supplied source length and operation semantics. |
| source_allocation / context | 16 | This allocation supplies the read operand, not the local overflowing destination. |
| caller_argument / context | 20 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 99-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the source object whose length drives the local destination write. |

## R06 — main, juliet-buffer-dest-cat

The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity.

Repair: The repaired caller selects or allocates a 100-byte destination.

Actual overflowing object: **stack**. Upstream family: `CWE121-dest-cat`.
[Prepared U](generated/R06_U.c) · [Fixed F](generated/R06_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s08/CWE121_Stack_Based_Buffer_Overflow__dest_char_alloca_cat_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 16 | The receiving object has fifty bytes. |
| access / sink | 9 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 7 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 8 | The explicit termination establishes the documented source length. |
| extent / extent | 9 | The count bound and/or string operation determines the access range together with the source facts. |
| destination_initialization / context | 19 | The destination initially denotes the empty string. |
| caller_argument / context | 20 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |
| alias_selection / context | 18 | The assignment identifies which allocated object is actually passed. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |

## R07 — main, juliet-buffer-CWE131-loop

The selected destination has 10 bytes. The operation requests ten int elements, a 40-byte access range on LP64.

Repair: The repaired allocation reserves 10*sizeof(int), or 40 bytes.

Actual overflowing object: **heap**. Upstream family: `CWE122-CWE131-loop`.
[Prepared U](generated/R07_U.c) · [Fixed F](generated/R07_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s05/CWE122_Heap_Based_Buffer_Overflow__CWE131_loop_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 19 | The receiving allocation reserves ten bytes, not ten int elements. |
| extent / extent | 7 | Ten int elements require 40 bytes; a first-invalid-store account is also acceptable. |
| access / sink | 9 | The operation writes through the selected destination pointer. |
| read_object / context | 5 | The read operand has ten int elements; its contents do not determine the copy count. |
| loop_index_type / context | 6 | The counter declaration supplies the type needed to justify its loop range; do not assume an omitted counter cannot wrap or saturate early. |
| caller_argument / context | 21 | The selected entry supplies this actual argument. |
| callee_parameter / context | 2 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The selected destination has 10 bytes. The operation requests ten int elements, a 40-byte access range on LP64. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |

## R08 — main, juliet-buffer-CWE806-snprintf

The receiving object has 50 bytes; the documented count and source facts imply a requested 99-byte access range, exceeding its capacity.

Repair: The repaired caller uses a shorter source.

Actual overflowing object: **stack**. Upstream family: `CWE121-CWE806-snprintf`.
[Prepared U](generated/R08_U.c) · [Fixed F](generated/R08_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s06/CWE121_Stack_Based_Buffer_Overflow__CWE806_char_alloca_snprintf_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 11 | The receiving object has fifty bytes. |
| access / sink | 12 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 21 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 22 | The explicit termination establishes the documented source length. |
| extent / extent | 12 | The access extent depends on the caller-supplied source length and operation semantics. |
| source_allocation / context | 19 | This allocation supplies the read operand, not the local overflowing destination. |
| macro_binding / context | 6 | On the selected Linux branch SNPRINTF denotes standard snprintf; do not invent an omitted binding. |
| caller_argument / context | 23 | The selected entry supplies this actual argument. |
| callee_parameter / context | 8 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |
| alias_selection / context | 20 | The assignment identifies which allocated object is actually passed. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 99-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the source object whose length drives the local destination write. |

## R09 — main, juliet-buffer-src-cat

The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity.

Repair: The repaired caller uses a shorter source.

Actual overflowing object: **stack**. Upstream family: `CWE122-c-src-cat`.
[Prepared U](generated/R09_U.c) · [Fixed F](generated/R09_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s10/CWE122_Heap_Based_Buffer_Overflow__c_src_char_cat_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 6 | The receiving object has fifty bytes. |
| access / sink | 7 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 17 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 18 | The explicit termination establishes the documented source length. |
| extent / extent | 7 | The access extent depends on the caller-supplied source length and operation semantics. |
| source_allocation / context | 15 | This allocation supplies the read operand, not the local overflowing destination. |
| caller_argument / context | 19 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the source object whose length drives the local destination write. |

## R10 — main, juliet-buffer-CWE805-snprintf

The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity.

Repair: The repaired caller selects or allocates a 100-byte destination.

Actual overflowing object: **stack**. Upstream family: `CWE121-CWE805-snprintf`.
[Prepared U](generated/R10_U.c) · [Fixed F](generated/R10_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s03/CWE121_Stack_Based_Buffer_Overflow__CWE805_char_alloca_snprintf_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 21 | The receiving object has fifty bytes. |
| access / sink | 14 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 12 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 13 | The explicit termination establishes the documented source length. |
| extent / extent | 14 | The count bound and/or string operation determines the access range together with the source facts. |
| macro_binding / context | 6 | On the selected Linux branch SNPRINTF denotes standard snprintf; do not invent an omitted binding. |
| caller_argument / context | 25 | The selected entry supplies this actual argument. |
| callee_parameter / context | 8 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |
| alias_selection / context | 23 | The assignment identifies which allocated object is actually passed. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |

## R12 — main, juliet-buffer-CWE806-ncat

The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity.

Repair: The repaired caller uses a shorter source.

Actual overflowing object: **stack**. Upstream family: `CWE121-CWE806-ncat`.
[Prepared U](generated/R12_U.c) · [Fixed F](generated/R12_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s06/CWE121_Stack_Based_Buffer_Overflow__CWE806_char_alloca_ncat_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 6 | The receiving object has fifty bytes. |
| access / sink | 7 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 17 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 18 | The explicit termination establishes the documented source length. |
| extent / extent | 7 | The access extent depends on the caller-supplied source length and operation semantics. |
| source_allocation / context | 15 | This allocation supplies the read operand, not the local overflowing destination. |
| caller_argument / context | 19 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |
| alias_selection / context | 16 | The assignment identifies which allocated object is actually passed. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the source object whose length drives the local destination write. |

## R13 — main, juliet-buffer-CWE805-copy

The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity.

Repair: The repaired caller selects or allocates a 100-byte destination.

Actual overflowing object: **heap**. Upstream family: `CWE122-c-CWE805-copy`.
[Prepared U](generated/R13_U.c) · [Fixed F](generated/R13_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s07/CWE122_Heap_Based_Buffer_Overflow__c_CWE805_char_memcpy_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 19 | The receiving object has fifty bytes. |
| access / sink | 9 | The intended write operation, not a later consequence or unrelated access. |
| extent / extent | 9 | The count argument requests 100 bytes; source initialization does not set this count. |
| read_object / context | 6 | The read operand has a hundred bytes; this is source-object context, not the write count. |
| caller_argument / context | 22 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |

## R14 — main, juliet-buffer-CWE193-loop

The source contains ten characters and a terminating NUL. The copy includes eleven bytes, while the selected destination has ten bytes.

Repair: The repaired caller selects the eleven-byte object.

Actual overflowing object: **stack**. Upstream family: `CWE121-CWE193-loop`.
[Prepared U](generated/R14_U.c) · [Fixed F](generated/R14_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s02/CWE121_Stack_Based_Buffer_Overflow__CWE193_char_alloca_loop_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 22 | The selected receiving object has ten bytes. |
| string_definition / context | 5 | The macro supplies ten non-NUL characters; it cannot be inferred when omitted. |
| source_initialization / extent | 9 | The source array is initialized with SRC_STRING. |
| extent / extent | 11, 12 | strcpy includes the NUL; the loop variant explicitly includes sourceLen + 1. |
| access / sink | 14 | The copy writes through the caller-selected pointer. |
| loop_index_type / context | 10 | The counter declaration supplies the type needed to justify its loop range; do not assume an omitted counter cannot wrap or saturate early. |
| caller_argument / context | 26 | The selected entry supplies this actual argument. |
| callee_parameter / context | 6 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |
| alias_selection / context | 24 | The assignment identifies which allocated object is actually passed. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The source contains ten characters and a terminating NUL. The copy includes eleven bytes, while the selected destination has ten bytes. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |

## R15 — assessor_holdout, juliet-buffer-dest-copy

The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity.

Repair: The repaired caller selects or allocates a 100-byte destination.

Actual overflowing object: **heap**. Upstream family: `CWE122-c-dest-copy`.
[Prepared U](generated/R15_U.c) · [Fixed F](generated/R15_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s10/CWE122_Heap_Based_Buffer_Overflow__c_dest_char_cpy_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 18 | The receiving object has fifty bytes. |
| access / sink | 9 | The intended write operation, not a later consequence or unrelated access. |
| source_initialization / extent | 7 | The documented non-NUL initialization establishes the source content relevant to length. |
| source_termination / context | 8 | The explicit termination establishes the documented source length. |
| extent / extent | 9 | The count bound and/or string operation determines the access range together with the source facts. |
| caller_argument / context | 21 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |

## R17 — assessor_holdout, juliet-buffer-CWE805-loop

The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity.

Repair: The repaired caller selects or allocates a 100-byte destination.

Actual overflowing object: **heap**. Upstream family: `CWE122-c-CWE805-loop`.
[Prepared U](generated/R17_U.c) · [Fixed F](generated/R17_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s07/CWE122_Heap_Based_Buffer_Overflow__c_CWE805_char_loop_41.c)

| Fact / role | U lines | Meaning |
|---|---|---|
| capacity / capacity | 23 | The receiving object has fifty bytes. |
| access / sink | 12 | The intended write operation, not a later consequence or unrelated access. |
| extent / extent | 10 | The loop explicitly ranges over one hundred char elements; contents do not set the count. |
| read_object / context | 7 | The read operand has a hundred bytes; this is source-object context, not the write count. |
| loop_index_type / context | 6 | The counter declaration supplies the type needed to justify its loop range; do not assume an omitted counter cannot wrap or saturate early. |
| caller_argument / context | 26 | The selected entry supplies this actual argument. |
| callee_parameter / context | 3 | The argument binds this formal parameter; equal spelling alone is not proof of identity. |

| Required relationship | Explanation |
|---|---|
| bounds_violation | The receiving object has 50 bytes; the documented count and source facts imply a requested 100-byte access range, exceeding its capacity. |
| extent_support | Establish the relevant count, source length or possible index using visible facts and permitted assumptions. |
| argument_binding | The caller supplies the destination object whose capacity is compared with the access. |
