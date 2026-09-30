# Vecta AI - Quick Start Guide

## Local Deployment

### Start the Service
```bash
./vecta start
```

The service automatically:
- Installs dependencies (Flask, pandas, numpy)
- Detects GPU (uses CUDA if available, falls back to CPU)
- Finds available port (8085-8150)
- Starts web server

Access: **http://localhost:8085**

### Manage the Service
```bash
./vecta status         # Check if running
./vecta logs           # View logs
./vecta stop           # Stop service
./vecta restart        # Restart
```

---

## HPC Deployment

### One-Time Setup
```bash
./vecta-hpc install
```

### Submit Job - GPU Mode (Default)
```bash
./vecta-hpc run gpu
```

**Default GPU Resources:**
- Partition: `gpu`
- GPUs: 1
- CPUs: 8
- Memory: 64G
- Time: 24 hours

**Custom GPU Resources:**
```bash
./vecta-hpc run gpu --gpus 2 --memory 128G --cpus 16 --time 48:00:00
```

### Submit Job - CPU Only
```bash
./vecta-hpc run cpu
```

**Default CPU Resources:**
- Partition: `standard`
- GPUs: 0 (none)
- CPUs: 16
- Memory: 32G
- Time: 24 hours

**Custom CPU Resources:**
```bash
./vecta-hpc run cpu --cpus 32 --memory 64G --time 48:00:00
```

### Manage HPC Jobs
```bash
./vecta-hpc status     # Check job status
./vecta-hpc logs       # View job logs
./vecta-hpc logs -f    # Follow logs (live)
./vecta-hpc stop       # Cancel job
./vecta-hpc list       # List all your jobs
```

---

## Resource Mode Comparison

| Feature | Local | HPC CPU | HPC GPU |
|---------|-------|---------|---------|
| **Auto-detect** | ✓ | - | - |
| **GPU Required** | Optional | No | Yes |
| **Speed** | Fast (GPU) / Medium (CPU) | Medium | Fast |
| **Setup** | `./vecta start` | `./vecta-hpc run cpu` | `./vecta-hpc run gpu` |
| **Best For** | Development, testing | Long batch jobs, no GPU | Production, fastest |

---

## Access Your Deployment

### Local
```
http://localhost:8085
```

### HPC
1. **Check node assignment:**
   ```bash
   ./vecta-hpc status
   ```

2. **SSH port forward from login node:**
   ```bash
   ssh -L 8085:compute-node:8085 username@login-node
   ```

3. **Access in browser:**
   ```
   http://localhost:8085
   ```

---

## Troubleshooting

### Local Issues

**Service won't start:**
```bash
./vecta stop           # Kill any existing process
pkill -f "python.*app.py"
./vecta start          # Try again
```

**Check logs:**
```bash
./vecta logs
tail -100 logs/vecta_service_*.log
```

### HPC Issues

**Job not starting:**
```bash
./vecta-hpc list       # Check queue
squeue -u $USER        # SLURM queue status
```

**Job failed:**
```bash
./vecta-hpc logs       # Check error logs
```

**Wrong partition:**
```bash
# Use custom partition
./vecta-hpc run gpu --partition gpu-v100
./vecta-hpc run cpu --partition standard-mem
```

---

## Advanced Options

### Custom Port (Local)
```bash
export VECTA_PORT=9000
./vecta start
```

### Custom Port (HPC)
```bash
./vecta-hpc run gpu --port 9000
```

### Different Time Limits
```bash
# Short job (4 hours)
./vecta-hpc run gpu --time 04:00:00

# Long job (7 days)
./vecta-hpc run cpu --time 168:00:00
```

### High-Memory Jobs
```bash
# GPU with lots of RAM
./vecta-hpc run gpu --memory 256G --gpus 4

# CPU with lots of RAM
./vecta-hpc run cpu --memory 512G --cpus 64
```

---

## Next Steps

- **Full Documentation**: See `DEPLOYMENT.md`
- **Learning System**: Visit `http://localhost:8085/learning`
- **Validation Portal**: Visit `http://localhost:8085/validator`
- **API Docs**: Check `/health` endpoint for service status

---

## Quick Reference Card

### Local Commands
```bash
./vecta start          # Start (auto GPU/CPU)
./vecta status         # Check status
./vecta logs           # View logs
./vecta stop           # Stop
./vecta restart        # Restart
```

### HPC Commands
```bash
./vecta-hpc install             # Setup
./vecta-hpc run gpu             # GPU mode
./vecta-hpc run cpu             # CPU mode
./vecta-hpc status              # Check job
./vecta-hpc logs                # View logs
./vecta-hpc stop                # Cancel
```

---

**Need Help?**
- GitHub: https://github.com/phindagijimana/vecta/issues
- Full Docs: `DEPLOYMENT.md`
- Self-Improvement: `SELF_IMPROVEMENT.md`
