"""Stand-alone fine-tuning script for LLMxCPG-D.

Same hyperparameters as Q (paper §4.2): LoRA r=8, α=4, lr=1e-4. Base model:
Qwen/QwQ-32B-Preview, chosen because Appendix B shows it beats Phi-4-14B,
Codestral-22B, and Qwen2.5-Coder-32B on PrimeVul.

Note: D is trained on *slices*, not raw code. Build the slice-labelled
training set first by running the bootstrap to get LLMxCPG-Q, then sweeping
your labelled training corpus through Q + Joern to produce slices, then
calling `llmxcpg.data.prepare.build_d_training_set`.

Run:
    python -m llmxcpg.training.train_d \
        --train-data data/d_train.jsonl \
        --output-dir checkpoints/llmxcpg-d
"""

from __future__ import annotations

import argparse
import logging


logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/QwQ-32B-Preview")
    parser.add_argument("--train-data", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-seq-length", type=int, default=8_192,
                        help="Slices are short by construction. 8K is enough.")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--per-device-batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    args = parser.parse_args()

    # The body is identical to train_q.py with a different default base model
    # and shorter max_seq_length. We delegate to the same helper.
    import sys
    from llmxcpg.training import train_q

    sys.argv = [
        "train_d",
        "--base-model", args.base_model,
        "--train-data", args.train_data,
        "--output-dir", args.output_dir,
        "--max-seq-length", str(args.max_seq_length),
        "--epochs", str(args.epochs),
        "--per-device-batch-size", str(args.per_device_batch_size),
        "--grad-accum", str(args.grad_accum),
        "--learning-rate", str(args.learning_rate),
    ]
    train_q.main()


if __name__ == "__main__":
    main()
