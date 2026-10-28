# Source-grounded mechanism references

Prepared before Q/Joern inference. These are AI-assisted source judgements, supported by the retained Juliet source, exact maps and executable witnesses; they are not independent annotations or excerpt-adequacy results.

Machine-readable references: `referents.jsonl`, mirrored in `development.jsonl` and `main.jsonl`. Map files connect each prepared line to its upstream line. The validation driver and headers are outside model inputs. Common assumptions and the adequacy rubric are in `PROTOCOL.md`.

## D01 — development, juliet-buffer-CWE131-copy

Allocation reserves 10 bytes, while ten int values require 10*sizeof(int), 40 bytes on the validated ABI. F reserves 10*sizeof(int).

Upstream family: `CWE121-CWE131-copy`. Actual overflowing object: **stack**.
[Prepared U](generated/D01_U.c) · [Fixed F](generated/D01_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__CWE131_memcpy_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 14 | 36 |
| extent (extent) | 6 | 26 |
| access (sink) | 6 | 26 |
| flow (context) | 15 | 37 |

Necessary relationships: Allocation reserves 10 bytes, while ten int values require 10*sizeof(int), 40 bytes on the validated ABI. F reserves 10*sizeof(int). Allocation reserves 10 bytes, while ten int values require 10*sizeof(int), 40 bytes on the validated ABI. F reserves 10*sizeof(int). The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## D02 — development, juliet-buffer-CWE129

Stdin 11 passes the nonnegative-only guard; index 11 exceeds a ten-int heap object's valid indices 0 through 9. The F counterpart adds the upper-bound guard.

Upstream family: `CWE122-c-CWE129`. Actual overflowing object: **heap**.
[Prepared U](generated/D02_U.c) · [Fixed F](generated/D02_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s06/CWE122_Heap_Based_Buffer_Overflow__c_CWE129_fgets_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| input (extent) | 36 | 65 |
| capacity (capacity) | 7 | 28 |
| guard (guard) | 13 | 37 |
| access (sink) | 15 | 39 |
| flow (context) | 43 | 72 |

Necessary relationships: Stdin 11 passes the nonnegative-only guard; index 11 exceeds a ten-int heap object's valid indices 0 through 9. The F counterpart adds the upper-bound guard. Stdin 11 passes the nonnegative-only guard; index 11 exceeds a ten-int heap object's valid indices 0 through 9. The F counterpart adds the upper-bound guard. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## D03 — development, juliet-buffer-CWE193-copy

The ten-character source includes its NUL: eleven bytes are written into the selected ten-byte stack buffer. F selects eleven bytes.

Upstream family: `CWE121-CWE193-copy`. Actual overflowing object: **stack**.
[Prepared U](generated/D03_U.c) · [Fixed F](generated/D03_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__CWE193_char_alloca_cpy_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 17 | 41 |
| extent (extent) | 5, 9 | 24, 31 |
| access (sink) | 10 | 33 |
| flow (context) | 19, 21 | 45, 47 |

Necessary relationships: The ten-character source includes its NUL: eleven bytes are written into the selected ten-byte stack buffer. F selects eleven bytes. The ten-character source includes its NUL: eleven bytes are written into the selected ten-byte stack buffer. F selects eleven bytes. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R02 — main, juliet-buffer-CWE805-ncat

The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object.

Upstream family: `CWE121-CWE805-ncat`. Actual overflowing object: **stack**.
[Prepared U](generated/R02_U.c) · [Fixed F](generated/R02_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s03/CWE121_Stack_Based_Buffer_Overflow__CWE805_char_alloca_ncat_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 16 | 38 |
| extent (extent) | 6, 7, 8 | 26, 27, 28 |
| access (sink) | 9 | 30 |
| flow (context) | 18, 20 | 42, 44 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object. The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R03 — main, juliet-buffer-CWE806-loop

The receiving object has 50 bytes; the documented initialization and operation write 99 bytes, exceeding its capacity. F uses a shorter source.

Upstream family: `CWE122-c-CWE806-loop`. Actual overflowing object: **stack**.
[Prepared U](generated/R03_U.c) · [Fixed F](generated/R03_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s09/CWE122_Heap_Based_Buffer_Overflow__c_CWE806_char_loop_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 6 | 26 |
| extent (extent) | 7, 8, 9, 23, 24 | 27, 28, 30, 46, 47 |
| access (sink) | 11 | 32 |
| flow (context) | 25 | 48 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 99 bytes, exceeding its capacity. F uses a shorter source. The receiving object has 50 bytes; the documented initialization and operation write 99 bytes, exceeding its capacity. F uses a shorter source. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R04 — main, juliet-buffer-src-copy

The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F uses a shorter source.

Upstream family: `CWE121-src-copy`. Actual overflowing object: **stack**.
[Prepared U](generated/R04_U.c) · [Fixed F](generated/R04_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s08/CWE121_Stack_Based_Buffer_Overflow__src_char_alloca_cpy_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 6 | 26 |
| extent (extent) | 16, 17 | 39, 40 |
| access (sink) | 7 | 28 |
| flow (context) | 18 | 41 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F uses a shorter source. The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F uses a shorter source. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R05 — main, juliet-buffer-CWE806-copy

The receiving object has 50 bytes; the documented initialization and operation write 99 bytes, exceeding its capacity. F uses a shorter source.

Upstream family: `CWE122-c-CWE806-copy`. Actual overflowing object: **stack**.
[Prepared U](generated/R05_U.c) · [Fixed F](generated/R05_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s09/CWE122_Heap_Based_Buffer_Overflow__c_CWE806_char_memcpy_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 6 | 26 |
| extent (extent) | 7, 18, 19 | 28, 41, 42 |
| access (sink) | 7 | 28 |
| flow (context) | 20 | 43 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 99 bytes, exceeding its capacity. F uses a shorter source. The receiving object has 50 bytes; the documented initialization and operation write 99 bytes, exceeding its capacity. F uses a shorter source. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R06 — main, juliet-buffer-dest-cat

The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object.

Upstream family: `CWE121-dest-cat`. Actual overflowing object: **stack**.
[Prepared U](generated/R06_U.c) · [Fixed F](generated/R06_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s08/CWE121_Stack_Based_Buffer_Overflow__dest_char_alloca_cat_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 16 | 38 |
| extent (extent) | 6, 7, 8 | 26, 27, 28 |
| access (sink) | 9 | 30 |
| flow (context) | 18, 20 | 42, 44 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object. The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R07 — main, juliet-buffer-CWE131-loop

Allocation reserves 10 bytes, while ten int values require 10*sizeof(int), 40 bytes on the validated ABI. F reserves 10*sizeof(int).

Upstream family: `CWE122-CWE131-loop`. Actual overflowing object: **heap**.
[Prepared U](generated/R07_U.c) · [Fixed F](generated/R07_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s05/CWE122_Heap_Based_Buffer_Overflow__CWE131_loop_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 19 | 41 |
| extent (extent) | 7 | 27 |
| access (sink) | 9 | 29 |
| flow (context) | 21 | 43 |

Necessary relationships: Allocation reserves 10 bytes, while ten int values require 10*sizeof(int), 40 bytes on the validated ABI. F reserves 10*sizeof(int). Allocation reserves 10 bytes, while ten int values require 10*sizeof(int), 40 bytes on the validated ABI. F reserves 10*sizeof(int). The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R08 — main, juliet-buffer-CWE806-snprintf

The receiving object has 50 bytes; the documented initialization and operation write 99 bytes, exceeding its capacity. F uses a shorter source.

Upstream family: `CWE121-CWE806-snprintf`. Actual overflowing object: **stack**.
[Prepared U](generated/R08_U.c) · [Fixed F](generated/R08_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s06/CWE121_Stack_Based_Buffer_Overflow__CWE806_char_alloca_snprintf_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 11 | 32 |
| extent (extent) | 12, 21, 22 | 34, 45, 46 |
| access (sink) | 12 | 34 |
| flow (context) | 23 | 47 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 99 bytes, exceeding its capacity. F uses a shorter source. The receiving object has 50 bytes; the documented initialization and operation write 99 bytes, exceeding its capacity. F uses a shorter source. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R09 — main, juliet-buffer-src-cat

The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F uses a shorter source.

Upstream family: `CWE122-c-src-cat`. Actual overflowing object: **stack**.
[Prepared U](generated/R09_U.c) · [Fixed F](generated/R09_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s10/CWE122_Heap_Based_Buffer_Overflow__c_src_char_cat_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 6 | 26 |
| extent (extent) | 17, 18 | 40, 41 |
| access (sink) | 7 | 28 |
| flow (context) | 19 | 42 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F uses a shorter source. The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F uses a shorter source. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R10 — main, juliet-buffer-CWE805-snprintf

The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object.

Upstream family: `CWE121-CWE805-snprintf`. Actual overflowing object: **stack**.
[Prepared U](generated/R10_U.c) · [Fixed F](generated/R10_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s03/CWE121_Stack_Based_Buffer_Overflow__CWE805_char_alloca_snprintf_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 21 | 44 |
| extent (extent) | 11, 12, 13 | 32, 33, 34 |
| access (sink) | 14 | 36 |
| flow (context) | 23, 25 | 48, 50 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object. The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R12 — main, juliet-buffer-CWE806-ncat

The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F uses a shorter source.

Upstream family: `CWE121-CWE806-ncat`. Actual overflowing object: **stack**.
[Prepared U](generated/R12_U.c) · [Fixed F](generated/R12_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s06/CWE121_Stack_Based_Buffer_Overflow__CWE806_char_alloca_ncat_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 6 | 26 |
| extent (extent) | 7, 17, 18 | 28, 40, 41 |
| access (sink) | 7 | 28 |
| flow (context) | 19 | 42 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F uses a shorter source. The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F uses a shorter source. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R13 — main, juliet-buffer-CWE805-copy

The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object.

Upstream family: `CWE122-c-CWE805-copy`. Actual overflowing object: **heap**.
[Prepared U](generated/R13_U.c) · [Fixed F](generated/R13_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE122_Heap_Based_Buffer_Overflow/s07/CWE122_Heap_Based_Buffer_Overflow__c_CWE805_char_memcpy_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 19 | 42 |
| extent (extent) | 6, 7, 8 | 26, 27, 28 |
| access (sink) | 9 | 30 |
| flow (context) | 22 | 45 |

Necessary relationships: The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object. The receiving object has 50 bytes; the documented initialization and operation write 100 bytes, exceeding its capacity. F selects a 100-byte receiving object. The selected caller argument reaches the sink parameter; do not assume this from hidden source.

## R14 — main, juliet-buffer-CWE193-loop

The ten-character source includes its NUL: eleven bytes are written into the selected ten-byte stack buffer. F selects eleven bytes.

Upstream family: `CWE121-CWE193-loop`. Actual overflowing object: **stack**.
[Prepared U](generated/R14_U.c) · [Fixed F](generated/R14_F.c) · [Pinned upstream](https://github.com/arichardson/juliet-test-suite-c/blob/f88433e3443648a17671398797a04ea1f8e1a274/testcases/CWE121_Stack_Based_Buffer_Overflow/s02/CWE121_Stack_Based_Buffer_Overflow__CWE193_char_alloca_loop_41.c)

| Role | Prepared U lines | Upstream lines |
|---|---|---|
| capacity (capacity) | 22 | 47 |
| extent (extent) | 5, 9, 10, 11, 12 | 24, 31, 32, 33, 36 |
| access (sink) | 14 | 38 |
| flow (context) | 24, 26 | 51, 53 |

Necessary relationships: The ten-character source includes its NUL: eleven bytes are written into the selected ten-byte stack buffer. F selects eleven bytes. The ten-character source includes its NUL: eleven bytes are written into the selected ten-byte stack buffer. F selects eleven bytes. The selected caller argument reaches the sink parameter; do not assume this from hidden source.
