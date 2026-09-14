"""Stand-alone fine-tuning script for LLMxCPG-Q.

The paper uses LLaMA-Factory; this is the equivalent in plain `peft + trl` so
you can read the training loop end-to-end. Same hyperparameters: LoRA r=8,
α=4, lr=1e-4, BF16. Base model: Qwen/Qwen2.5-Coder-32B-Instruct.

Run:
    python -m llmxcpg.training.train_q \
        --train-data data/q_train.jsonl \
        --output-dir checkpoints/llmxcpg-q
"""

from __future__ import annotations

import argparse
import logging

from llmxcpg.config import TrainingConfig

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-Coder-32B-Instruct")
    parser.add_argument("--train-data", required=True, help="JSONL in alpaca format")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-seq-length", type=int, default=32_768,
                        help="Paper §5 fine-tuned at 32K. Drop to 8192 for limited GPUs.")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--per-device-batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--lora-rank", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=4)
    parser.add_argument("--template", choices=("qwen", "raw"), default="qwen",
                        help="Q uses Qwen chat; the released D serialization is raw.")
    args = parser.parse_args()

    # Lazy imports — these are heavy and unnecessary unless you actually train.
    import torch
    from datasets import load_dataset
    from peft import get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForSeq2Seq,
        Trainer,
        TrainingArguments,
    )

    from llmxcpg.training.lora_config import build_lora_config

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")

    cfg = TrainingConfig(
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
        learning_rate=args.learning_rate,
        num_epochs=args.epochs,
        per_device_train_batch_size=args.per_device_batch_size,
        gradient_accumulation_steps=args.grad_accum,
    )

    logger.info("Loading base model: %s", args.base_model)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model = get_peft_model(model, build_lora_config(cfg))
    model.print_trainable_parameters()

    # Load alpaca-format data and collate as instruction → output.
    raw = load_dataset("json", data_files=args.train_data, split="train")

    def to_prompt_response(example: dict) -> dict:
        instruction = example["instruction"]
        input_text = example.get("input") or ""
        content = instruction + (
            ("\n" if not instruction.endswith("\n") else "") + input_text
            if input_text else ""
        )
        if args.template == "qwen":
            if not tokenizer.chat_template:
                raise ValueError("The selected Q tokenizer does not define a chat template.")
            prompt = tokenizer.apply_chat_template(
                [{"role": "user", "content": content}],
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            prompt = content
        return {"prompt": prompt, "response": example["output"]}

    raw = raw.map(to_prompt_response, remove_columns=raw.column_names)

    def tokenize(example):
        prompt_ids = tokenizer(
            example["prompt"], add_special_tokens=False,
        )["input_ids"]
        response_ids = tokenizer(
            example["response"] + tokenizer.eos_token,
            add_special_tokens=False,
        )["input_ids"]
        if len(response_ids) >= args.max_seq_length:
            response_ids = response_ids[:args.max_seq_length]
            prompt_ids = []
        else:
            prompt_ids = prompt_ids[-(args.max_seq_length - len(response_ids)):]
        input_ids = prompt_ids + response_ids
        return {
            "input_ids": input_ids,
            "attention_mask": [1] * len(input_ids),
            "labels": [-100] * len(prompt_ids) + response_ids,
        }

    tokenised = raw.map(tokenize, remove_columns=["prompt", "response"])

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=cfg.num_epochs,
        per_device_train_batch_size=cfg.per_device_train_batch_size,
        gradient_accumulation_steps=cfg.gradient_accumulation_steps,
        learning_rate=cfg.learning_rate,
        warmup_ratio=cfg.warmup_ratio,
        weight_decay=cfg.weight_decay,
        bf16=cfg.bf16,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        report_to="none",
        gradient_checkpointing=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenised,
        tokenizer=tokenizer,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            model=model,
            label_pad_token_id=-100,
            padding=True,
        ),
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    logger.info("Saved adapters + tokenizer to %s", args.output_dir)


if __name__ == "__main__":
    main()
