#!/usr/bin/env python3
"""Figure S3 — LoRA fine-tune validation loss per epoch.

Numbers are from `checkpoints/llama3-med42-8b_lora_epi/checkpoint-*/trainer_state.json`
after SLURM 143696 completed. The best epoch (3) was retained via
`load_best_model_at_end=True`; the training script would have early-stopped
at epoch 5 with patience 2 as the loss climbed above the epoch-3 minimum.

Run:
    venv/bin/python writing/figures/make_fig_s3_val_loss.py
Outputs writing/figures/fig_s3_val_loss.png (300 dpi) and .pdf.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent

# Epoch → validation loss, from trainer_state.json across the 5 checkpoints.
epochs = [1, 2, 3, 4, 5]
val_loss = [0.01008, 0.00979, 0.00952, 0.00958, 0.01030]
best_epoch = 3


def main() -> None:
    fig, ax = plt.subplots(figsize=(4.5, 3.0), dpi=150)
    ax.plot(epochs, val_loss, marker="o", linewidth=1.8, color="#2b6cb0",
            label="validation loss")
    # Mark the best-epoch point.
    ax.scatter([best_epoch], [val_loss[best_epoch - 1]], s=140, zorder=5,
               facecolor="none", edgecolor="#c05621", linewidth=2.0,
               label=f"best epoch (n = {best_epoch}, loss = {val_loss[best_epoch - 1]:.5f})")
    # Reference line for the retained checkpoint.
    ax.axhline(val_loss[best_epoch - 1], linestyle=":", linewidth=0.8,
               color="#c05621", alpha=0.6)

    ax.set_xlabel("Epoch")
    ax.set_ylabel("Cross-entropy loss (target tokens only)")
    ax.set_xticks(epochs)
    ax.set_title(
        "LoRA fine-tune validation loss — MedAI-EPI-tuned Med42-8B\n"
        "corpus: synth+fs (1078 train / 122 val, patient-level split)",
        fontsize=9,
    )
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper center", fontsize=8, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        out = HERE / f"fig_s3_val_loss.{ext}"
        fig.savefig(out, bbox_inches="tight")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
