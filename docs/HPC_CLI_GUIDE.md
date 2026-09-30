# HPC CLI Guide - vecta-hpc

## Overview

The `vecta-hpc` CLI tool manages Vecta AI deployment on HPC clusters with SLURM job scheduling.

---

## Commands

### Installation

```bash
./vecta-hpc install [OPTIONS]
```

Installs Vecta AI on HPC cluster, including:
- Python dependencies (Flask, pandas, numpy)
- Optional GPU packages (PyTorch, transformers)
- SLURM job script creation
- Environment setup

**Options:**
- `--partition` - SLURM partition (default: gpu)
- `--gpus` - Number of GPUs (default: 1)
- `--memory` - Memory allocation (default: 64G)
- `--time` - Time limit (default: 24:00:00)
- `--cpus` - CPUs per task (default: 8)
- `--port` - Service port (default: 8085)

**Example:**
```bash
# Basic installation
./vecta-hpc install

# Custom resources
./vecta-hpc install --gpus 2 --memory 128G --time 48:00:00
```

---

### Run Job

```bash
./vecta-hpc run [OPTIONS]
```

Submits Vecta AI job to SLURM queue.

**Options:** Same as install command (overrides defaults)

**Example:**
```bash
# Submit with defaults
./vecta-hpc run

# Submit with 2 GPUs and 128GB RAM
./vecta-hpc run --gpus 2 --memory 128G

# Submit to specific partition
./vecta-hpc run --partition gpu-long --time 72:00:00
```

**Output:**
```
[OK] Job submitted successfully
     Job ID: 123456

Next steps:
  Check status: ./vecta-hpc status
  View logs:    ./vecta-hpc logs
  Cancel job:   ./vecta-hpc stop
```

---

### Check Status

```bash
./vecta-hpc status
```

Shows current job status and access information.

**Output when running:**
```
Checking job: 123456

JOBID    PARTITION  STATE     NODELIST    TIME
123456   gpu        RUNNING   gpu-node-01 1:23:45

[OK] Job is RUNNING

Access Vecta AI:
  1. From login node, forward port:
     ssh -L 8085:gpu-node-01:8085 $USER@login-node
  2. Access from browser:
     http://localhost:8085
```

---

### View Logs

```bash
./vecta-hpc logs [OPTIONS]
```

View job output and error logs.

**Options:**
- `-n, --lines N` - Show last N lines (default: 50)
- `-f, --follow` - Follow log output (like tail -f)

**Examples:**
```bash
# View last 50 lines
./vecta-hpc logs

# View last 200 lines
./vecta-hpc logs -n 200

# Follow live log output
./vecta-hpc logs --follow
```

---

### Stop Job

```bash
./vecta-hpc stop
```

Cancels running SLURM job.

**Example:**
```bash
./vecta-hpc stop

# Output:
Cancelling job: 123456
[OK] Job 123456 cancelled
```

---

### List Jobs

```bash
./vecta-hpc list
```

Shows all your SLURM jobs.

**Example:**
```bash
./vecta-hpc list

# Output:
Your SLURM jobs:
JOBID    PARTITION  NAME       USER     ST  TIME
123456   gpu        vecta-ai   username R   2:30:15
123457   gpu        vecta-ai   username PD  0:00
```

---

### Environment Info

```bash
./vecta-hpc info
```

Shows HPC environment information:
- SLURM status
- Available GPUs
- Loaded modules
- Python version
- CUDA availability

---

### Configuration

```bash
./vecta-hpc config
```

Shows current configuration:
- SLURM job script settings
- Installation status
- Active job ID

---

## Complete Workflow

### First Time Setup

```bash
# 1. Load required modules
module load cuda/12.2 python/3.9 gcc/11.2

# 2. Install Vecta AI
./vecta-hpc install

# Installation will:
# - Install Python packages
# - Optionally install GPU packages
# - Create SLURM job script
# - Setup logs directory
```

### Submit and Monitor Job

```bash
# 3. Submit job
./vecta-hpc run

# 4. Check status
./vecta-hpc status

# 5. View logs
./vecta-hpc logs

# 6. When ready, access the app
# (follow instructions from status command)
```

### Access Application

From login node:
```bash
# Get job info
./vecta-hpc status

# Output will show node and port
# Example: gpu-node-01, port 8085

# Forward port (in new terminal)
ssh -L 8085:gpu-node-01:8085 username@login-node

# Open browser on your local machine
# Navigate to: http://localhost:8085
```

### Stop When Done

```bash
# Cancel job
./vecta-hpc stop

# Verify stopped
./vecta-hpc status
```

---

## Comparison: vecta vs vecta-hpc

### Local Deployment (vecta)

```bash
# Start on local machine
./vecta start

# Direct access
http://localhost:8085

# Stop
./vecta stop
```

**Use when:**
- Running on local workstation
- Direct access to hardware
- Development/testing
- Single-user deployment

### HPC Deployment (vecta-hpc)

```bash
# Submit to SLURM
./vecta-hpc run

# Access via SSH tunnel
ssh -L 8085:node:8085 user@hpc

# Cancel job
./vecta-hpc stop
```

**Use when:**
- Running on HPC cluster
- Shared computing resources
- Batch processing
- Queue-based scheduling

---

## Advanced Usage

### Custom Resource Allocation

```bash
# Large memory job
./vecta-hpc run --memory 256G --gpus 4

# Extended time
./vecta-hpc run --time 96:00:00

# Specific partition
./vecta-hpc run --partition gpu-a100
```

### Multiple Jobs

```bash
# Submit first job
./vecta-hpc run --port 8085

# Submit second job (different port)
./vecta-hpc run --port 8086
```

### Debugging

```bash
# Check environment
./vecta-hpc info

# View detailed logs
./vecta-hpc logs -n 1000

# Check SLURM queue
./vecta-hpc list

# View job history
sacct -u $USER --format=JobID,JobName,State,Elapsed
```

---

## Troubleshooting

### Installation Issues

**Problem:** Module load failures
```bash
# Solution: Check available modules
module avail cuda
module avail python

# Load correct versions
module load cuda/12.2
module load python/3.9
```

**Problem:** pip install fails
```bash
# Solution: Use --user flag
pip3 install --user package-name

# Or create virtual environment
python3 -m venv ~/vecta-env
source ~/vecta-env/bin/activate
```

### Job Issues

**Problem:** Job stays PENDING
```bash
# Check reason
squeue -j JOBID --Format=Reason

# Check partition availability
sinfo -p gpu
```

**Problem:** Job fails immediately
```bash
# View error log
./vecta-hpc logs

# Check error file
cat logs/vecta_JOBID.err
```

**Problem:** Can't access application
```bash
# Verify job is running
./vecta-hpc status

# Check port forwarding
ssh -L 8085:node:8085 -v user@hpc

# Test from compute node
ssh compute-node
curl http://localhost:8085/health
```

### Network Issues

**Problem:** Port forwarding not working
```bash
# Solution 1: Verify node name
squeue -j JOBID -o "%N"

# Solution 2: Test on compute node first
ssh compute-node-01
curl http://localhost:8085

# Solution 3: Use full hostname
ssh -L 8085:compute-node-01.hpc.domain.edu:8085 user@login
```

---

## File Locations

### Created by vecta-hpc

```
vecta-ai/
├── .hpc_installed          # Installation marker
├── .hpc_job_id            # Current job ID
├── slurm_job.sh           # SLURM batch script
└── logs/
    ├── vecta_123456.out   # Job output
    └── vecta_123456.err   # Job errors
```

### Configuration Files

- **Job Script**: `slurm_job.sh` - SLURM batch script
- **Installation**: `.hpc_installed` - Timestamp of installation
- **Job Tracking**: `.hpc_job_id` - Current active job ID

---

## Example Session

```bash
# Session 1: Setup
$ ./vecta-hpc install
Installing Vecta AI on HPC cluster...
Step 1/5: Loading required modules...
Step 2/5: Installing Python dependencies...
Step 3/5: Creating SLURM job script...
Step 4/5: Creating logs directory...
Step 5/5: Marking installation complete...
[OK] Installation Complete!

# Session 2: Submit job
$ module load cuda/12.2 python/3.9
$ ./vecta-hpc run
Job submitted successfully
Job ID: 987654

$ ./vecta-hpc status
Job is RUNNING on gpu-node-05

# Session 3: Access (from local machine)
$ ssh -L 8085:gpu-node-05:8085 username@hpc.university.edu
# Open browser: http://localhost:8085

# Session 4: Monitor
$ ./vecta-hpc logs --follow
[Watching logs in real-time...]

# Session 5: Cleanup
$ ./vecta-hpc stop
Job 987654 cancelled
```

---

## Best Practices

### Resource Requests

1. **Start Conservative**: Request minimal resources initially
   ```bash
   ./vecta-hpc run --gpus 1 --memory 64G
   ```

2. **Monitor Usage**: Check actual resource usage
   ```bash
   sstat -j JOBID --format=MaxRSS,AveCPU
   ```

3. **Adjust as Needed**: Increase for subsequent jobs
   ```bash
   ./vecta-hpc run --memory 128G  # After seeing actual usage
   ```

### Job Management

1. **Regular Monitoring**: Check status periodically
   ```bash
   watch -n 60 './vecta-hpc status'
   ```

2. **Log Review**: Review logs for errors
   ```bash
   ./vecta-hpc logs | grep -i error
   ```

3. **Cleanup**: Cancel jobs when done
   ```bash
   ./vecta-hpc stop
   ```

### Data Management

1. **Input Data**: Place in project directory before submission
2. **Output Data**: Save results before job ends
3. **Logs**: Archive logs periodically
   ```bash
   tar -czf logs_$(date +%Y%m%d).tar.gz logs/
   ```

---

## Security Considerations

### SSH Tunneling

Always use SSH port forwarding for secure access:
```bash
# Good: Encrypted tunnel
ssh -L 8085:node:8085 user@hpc

# Bad: Direct access (if allowed)
http://node:8085  # Not encrypted
```

### Data Privacy

- Don't include PHI in logs
- Use secure file transfers (scp, rsync)
- Follow institutional policies

### Access Control

- Use strong passwords
- Enable 2FA if available
- Don't share credentials

---

## Performance Tips

### GPU Utilization

Monitor GPU usage during job:
```bash
# On compute node
ssh compute-node
watch -n 1 nvidia-smi
```

### Memory Optimization

If running out of memory:
```bash
# Enable 8-bit quantization in app.py
# Reduces VRAM by 50%

# Or request more memory
./vecta-hpc run --memory 128G
```

### Multi-GPU

For faster processing:
```bash
# Use multiple GPUs
./vecta-hpc run --gpus 4

# App will automatically use all GPUs
```

---

## Integration with vecta (Local CLI)

Both CLIs can coexist:

```bash
# Local development
./vecta start              # Run locally

# HPC production
./vecta-hpc run           # Run on HPC

# Both use same codebase
# Both access same data files
# Different deployment environments
```

---

## Support

### Getting Help

```bash
# Command help
./vecta-hpc --help
./vecta-hpc COMMAND --help

# Check environment
./vecta-hpc info

# View configuration
./vecta-hpc config
```

### Common Commands Reference

```bash
# Setup
module load cuda python gcc
./vecta-hpc install

# Run
./vecta-hpc run
./vecta-hpc status
./vecta-hpc logs

# Manage
./vecta-hpc stop
./vecta-hpc list

# Info
./vecta-hpc info
./vecta-hpc config
```

---

**CLI Version**: 1.0  
**Last Updated**: 2026-02-13  
**Status**: Production Ready
