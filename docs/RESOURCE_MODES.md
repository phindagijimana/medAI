# Vecta AI Resource Modes Guide

## Overview

Vecta AI offers flexible deployment options optimized for different computing environments. Choose the right mode for your use case:

## Deployment Modes

### 1. Local Deployment (Auto-Detection)
**Command:** `./vecta start`

**Behavior:**
- Automatically detects available GPU
- Uses CUDA if GPU found
- Falls back to CPU if no GPU available
- No manual configuration needed

**Best For:**
- Development
- Testing
- Single-user access
- Quick prototyping

```bash
./vecta start          # Auto-detects GPU/CPU
# Check logs to see which mode was selected
./vecta logs | grep "GPU detected"
```

---

### 2. HPC CPU Mode
**Command:** `./vecta-hpc run cpu`

**Resources:**
- **Partition:** `standard` (default)
- **GPUs:** 0 (none)
- **CPUs:** 16 cores (default)
- **Memory:** 32GB (default)
- **Time:** 24 hours (default)

**Best For:**
- No GPU available
- CPU-only partitions
- Cost-sensitive deployments
- Sufficient for tabular analysis and rule-based features

**Examples:**
```bash
# Default CPU configuration
./vecta-hpc run cpu

# High-memory CPU job
./vecta-hpc run cpu --cpus 32 --memory 128G

# Long-running CPU job
./vecta-hpc run cpu --time 168:00:00 --cpus 16

# Custom partition
./vecta-hpc run cpu --partition standard-mem
```

**Performance:**
- Tabular analysis: Fast
- Rule-based features: Fast
- AI model inference: Slow (if PyTorch installed)
- Best for: Non-AI workloads

---

### 3. HPC GPU Mode
**Command:** `./vecta-hpc run gpu`

**Resources:**
- **Partition:** `gpu` (default)
- **GPUs:** 1 (default)
- **CPUs:** 8 cores (default)
- **Memory:** 64GB (default)
- **Time:** 24 hours (default)

**Best For:**
- Full AI model capabilities
- Fastest inference
- Production workloads
- High-throughput analysis

**Examples:**
```bash
# Default GPU configuration
./vecta-hpc run gpu

# Multi-GPU job
./vecta-hpc run gpu --gpus 2 --memory 128G

# High-memory GPU job
./vecta-hpc run gpu --gpus 4 --memory 256G --cpus 16

# Custom GPU partition
./vecta-hpc run gpu --partition gpu-v100 --gpus 2
```

**Performance:**
- Tabular analysis: Fast
- Rule-based features: Fast
- AI model inference: Very Fast
- Best for: Full-featured AI analysis

---

## Resource Comparison

| Feature | Local | HPC CPU | HPC GPU |
|---------|-------|---------|---------|
| **Setup** | `./vecta start` | `./vecta-hpc run cpu` | `./vecta-hpc run gpu` |
| **GPU Detection** | Automatic | Manual (none) | Manual (specified) |
| **Default CPUs** | All available | 16 | 8 |
| **Default Memory** | System dependent | 32GB | 64GB |
| **Default GPUs** | Auto-detect (0-1) | 0 | 1 |
| **Partition** | N/A | standard | gpu |
| **AI Model** | Optional | Slow | Fast |
| **Cost** | Free (local hardware) | Lower | Higher |
| **Scalability** | Limited | High | High |
| **Queue Time** | Instant | Short | Variable |

---

## Choosing the Right Mode

### Use Local Mode When:
- ✓ Developing or testing
- ✓ Single user access
- ✓ Have local GPU available
- ✓ Need immediate access
- ✓ Iterating on features

### Use CPU Mode When:
- ✓ No GPU available or needed
- ✓ Tabular analysis only
- ✓ Cost-sensitive
- ✓ Long batch jobs
- ✓ CPU partitions have better availability

### Use GPU Mode When:
- ✓ Need full AI capabilities
- ✓ High-throughput required
- ✓ Production deployment
- ✓ Speed is critical
- ✓ Processing medical text/documents with AI

---

## Performance Benchmarks

### Tabular Data Analysis (1000 rows)
- **Local (GPU):** ~2 seconds
- **Local (CPU):** ~3 seconds
- **HPC CPU:** ~2-3 seconds
- **HPC GPU:** ~1-2 seconds

### AI Model Inference (Single Case)
- **Local (GPU):** ~5 seconds (first run ~30s for load)
- **Local (CPU):** ~60 seconds (first run ~90s)
- **HPC CPU:** ~60 seconds
- **HPC GPU:** ~5 seconds (first run ~30s)

### Batch Processing (100 cases)
- **Local (GPU):** ~8 minutes
- **Local (CPU):** ~100 minutes
- **HPC CPU (16 cores):** ~90 minutes
- **HPC GPU (1 GPU):** ~7 minutes
- **HPC GPU (4 GPUs):** ~2 minutes

---

## Resource Allocation Guidelines

### For Development/Testing
```bash
./vecta start          # Auto-detect, simplest option
```

### For Small-Scale Production (<100 cases/day)
```bash
./vecta-hpc run cpu --cpus 8 --memory 32G
```

### For Medium-Scale Production (100-1000 cases/day)
```bash
./vecta-hpc run gpu --gpus 1 --memory 64G
```

### For Large-Scale Production (>1000 cases/day)
```bash
./vecta-hpc run gpu --gpus 4 --memory 256G --cpus 32
```

---

## Advanced Configuration

### Custom Partitions
Your HPC cluster may have specialized partitions:

```bash
# CPU partitions
./vecta-hpc run cpu --partition standard
./vecta-hpc run cpu --partition high-mem
./vecta-hpc run cpu --partition long-jobs

# GPU partitions
./vecta-hpc run gpu --partition gpu-a100
./vecta-hpc run gpu --partition gpu-v100
./vecta-hpc run gpu --partition gpu-shared
```

### Time Limits
Adjust based on expected runtime:

```bash
# Short job (4 hours)
./vecta-hpc run gpu --time 04:00:00

# Standard job (24 hours)
./vecta-hpc run gpu --time 24:00:00

# Long job (7 days)
./vecta-hpc run cpu --time 168:00:00
```

### Memory Scaling
Match memory to workload:

```bash
# Small datasets (<1000 rows)
./vecta-hpc run cpu --memory 16G

# Medium datasets (1000-10000 rows)
./vecta-hpc run cpu --memory 64G

# Large datasets (>10000 rows)
./vecta-hpc run cpu --memory 256G

# AI model with large batches
./vecta-hpc run gpu --memory 128G
```

---

## Troubleshooting

### "GPU not found" on Local
```bash
# Check if CUDA is available
python3 -c "import torch; print(torch.cuda.is_available())"

# If False, service will auto-fallback to CPU
./vecta logs | grep "No GPU detected"
```

### "Partition not found" on HPC
```bash
# Check available partitions
sinfo -s

# Use correct partition name
./vecta-hpc run gpu --partition gpu-standard
```

### "Out of Memory" Errors
```bash
# Increase memory allocation
./vecta-hpc run gpu --memory 128G

# Or reduce batch size in app config
```

### Job Stuck in Queue
```bash
# Check queue status
./vecta-hpc status
squeue -u $USER

# Try different partition with better availability
./vecta-hpc run cpu --partition standard
```

---

## Environment Variables

### Override Defaults Globally
```bash
# Set default port
export VECTA_PORT=9000

# Set default partition
export VECTA_PARTITION=gpu-a100

# Apply to commands
./vecta start
./vecta-hpc run gpu
```

---

## Migration Guide

### From Fixed GPU to Flexible Modes
**Old:**
```bash
./vecta-hpc run --gpus 1
```

**New:**
```bash
./vecta-hpc run gpu          # GPU mode
./vecta-hpc run gpu --gpus 2 # Custom GPU count
./vecta-hpc run cpu          # CPU-only mode
```

### From Manual Module Loading
**Old:**
```bash
module load cuda python gcc
./vecta-hpc run
```

**New:**
```bash
# Modules auto-loaded based on mode
./vecta-hpc run gpu   # Loads cuda, python, gcc
./vecta-hpc run cpu   # Loads python, gcc (no cuda)
```

---

## Best Practices

1. **Development:** Use local mode for fastest iteration
2. **Testing:** Use CPU mode for cost-effective validation
3. **Production:** Use GPU mode for performance
4. **Batch Jobs:** Use CPU mode with many cores for parallel processing
5. **Long Jobs:** Use CPU mode to avoid GPU queue times

---

## FAQ

**Q: Which mode is fastest?**  
A: GPU mode for AI inference, CPU mode can be competitive for tabular-only analysis.

**Q: Do I need a GPU for Vecta AI?**  
A: No, all features work on CPU. AI model inference is slower but functional.

**Q: Can I switch modes after deployment?**  
A: Yes! Stop the current job and restart with a different mode.

**Q: What if my HPC doesn't have GPU partition?**  
A: Use CPU mode exclusively. Performance is still good for tabular features.

**Q: How much does GPU mode cost?**  
A: Varies by HPC facility. Typically 2-5x CPU cost, but 10-20x faster for AI tasks.

---

**See Also:**
- `QUICK_START.md` - Getting started guide
- `DEPLOYMENT.md` - Full deployment documentation
- `SELF_IMPROVEMENT.md` - Learning system docs
