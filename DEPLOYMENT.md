# Deployment Guide - Vecta AI

Complete deployment guide for Vecta AI neurology analysis platform.

## Quick Start

### One-Command Setup (Local)

```bash
git clone https://github.com/phindagijimana/vecta.git
cd vecta
./vecta start
```

Access at http://localhost:8085

### One-Command Setup (HPC)

```bash
git clone https://github.com/phindagijimana/vecta.git
cd vecta
./vecta-hpc install
./vecta-hpc run gpu     # GPU mode (default)
# OR
./vecta-hpc run cpu     # CPU-only mode
```

## Deployment Options

### 1. Local Workstation

**Requirements:**
- Python 3.8+
- 2GB RAM minimum
- 16GB+ GPU VRAM (optional, for AI model)

**Resource Detection:**
The local deployment automatically detects available resources:
- **GPU Available**: Uses GPU acceleration (CUDA)
- **No GPU**: Falls back to CPU mode
- No manual configuration needed!

**Quick Start:**
```bash
./vecta start          # Auto-installs dependencies & detects GPU/CPU
```

**Manual Setup:**
```bash
pip3 install --user flask flask-cors pandas numpy
python3 app.py
```

**CLI Commands:**
```bash
./vecta start          # Start service
./vecta status         # Check status
./vecta logs           # View logs
./vecta stop           # Stop service
./vecta restart        # Restart service
```

**Features:**
- Auto-installs Flask dependencies
- Auto-detects GPU/CPU resources
- Smart port detection (8085-8150)
- PID tracking
- Log management

### 2. HPC Cluster (SLURM)

**Requirements:**
- SLURM workload manager
- Python 3.8+ module
- CUDA module (for GPU mode)
- GPU partition access (for GPU mode)

**Resource Modes:**
Choose between CPU-only or GPU-accelerated deployment:

| Mode | Resources | Use Case |
|------|-----------|----------|
| `gpu` | CPU + GPU | Full AI model, faster analysis |
| `cpu` | CPU only | No GPU needed, slower but functional |

**Installation:**
```bash
# One-time setup (modules auto-loaded)
./vecta-hpc install
```

**Submit Job (GPU Mode - Default):**
```bash
# Default GPU configuration
./vecta-hpc run gpu

# Custom GPU resources
./vecta-hpc run gpu --gpus 2 --memory 128G --cpus 8
```

**Submit Job (CPU-Only Mode):**
```bash
# Default CPU configuration
./vecta-hpc run cpu

# Custom CPU resources
./vecta-hpc run cpu --cpus 32 --memory 64G --time 48:00:00
```

**Resource Defaults:**

| Mode | Partition | GPUs | CPUs | Memory | Time |
|------|-----------|------|------|--------|------|
| GPU | `gpu` | 1 | 8 | 64G | 24h |
| CPU | `standard` | 0 | 16 | 32G | 24h |

**Additional Commands:**
```bash
# Default resources (1 GPU, 64GB, 24h)
./vecta-hpc run

# Custom resources
./vecta-hpc run --gpus 2 --memory 128G --time 48:00:00
```

**Monitor Job:**
```bash
./vecta-hpc status     # Check job status
./vecta-hpc logs       # View logs
./vecta-hpc logs -f    # Follow logs
```

**Access Application:**
```bash
# Get node info
./vecta-hpc status

# Forward port (from local machine)
ssh -L 8085:gpu-node-XX:8085 username@hpc-login.edu

# Access in browser
http://localhost:8085
```

**Stop Job:**
```bash
./vecta-hpc stop
```

**HPC CLI Options:**

Installation customization:
```bash
./vecta-hpc install \
  --partition gpu \
  --gpus 1 \
  --memory 64G \
  --time 24:00:00 \
  --cpus 8 \
  --port 8085
```

Job submission:
```bash
# Large memory job
./vecta-hpc run --memory 256G --gpus 4

# Extended time
./vecta-hpc run --time 96:00:00

# Specific partition
./vecta-hpc run --partition gpu-a100
```

Monitoring:
```bash
./vecta-hpc list       # List all jobs
./vecta-hpc info       # Environment info
./vecta-hpc config     # View configuration
```

**Troubleshooting HPC:**

Job stays PENDING:
```bash
squeue -j JOBID --Format=Reason
sinfo -p gpu
```

Job fails immediately:
```bash
./vecta-hpc logs
cat logs/vecta_JOBID.err
```

Port forwarding issues:
```bash
# Verify node name
squeue -j JOBID -o "%N"

# Test on compute node
ssh compute-node-01
curl http://localhost:8085
```

### 3. Docker Deployment

**With GPU:**
```bash
# Build image
docker build -t vecta-ai .

# Run with GPU
docker run -d \
  --gpus all \
  -p 8085:8085 \
  -v $(pwd)/data:/app/data \
  vecta-ai
```

**CPU Only:**
```bash
docker run -d \
  -p 8085:8085 \
  -v $(pwd)/data:/app/data \
  vecta-ai
```

**Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8085

# Run app
CMD ["python3", "app.py"]
```

### 4. Production Server

**Using Gunicorn:**

Use the checked-in `gunicorn_config.py` (defaults to **one worker** so only one copy of the LLM is loaded). Increase `GUNICORN_WORKERS` only if you intentionally run multiple model processes.

```bash
pip3 install gunicorn
gunicorn -c gunicorn_config.py app:app
```

**Systemd Service:**

Create `/etc/systemd/system/vecta.service`:
```ini
[Unit]
Description=Vecta AI Service
After=network.target

[Service]
Type=simple
User=vecta
WorkingDirectory=/opt/vecta
ExecStart=/usr/bin/python3 /opt/vecta/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable vecta
sudo systemctl start vecta
sudo systemctl status vecta
```

**Nginx Reverse Proxy:**

Configure `/etc/nginx/sites-available/vecta`:
```nginx
server {
    listen 80;
    server_name vecta.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8085;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/vecta /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Cloud GPU Deployment

**AWS EC2 (P3/G5 instances):**
```bash
# Launch GPU instance
# Install CUDA toolkit
sudo apt update
sudo apt install nvidia-cuda-toolkit

# Clone and run
git clone https://github.com/phindagijimana/vecta.git
cd vecta
./vecta start
```

**Google Cloud (A100/T4):**
```bash
# Create GPU instance
gcloud compute instances create vecta-gpu \
  --zone=us-central1-a \
  --machine-type=n1-standard-8 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --image-family=pytorch-latest-gpu \
  --image-project=deeplearning-platform-release

# Deploy
./vecta start
```

**Azure (NC/ND series):**
```bash
# Create GPU VM
az vm create \
  --resource-group vecta-rg \
  --name vecta-gpu \
  --size Standard_NC6 \
  --image UbuntuLTS

# Deploy
./vecta start
```

## GPU Setup

### NVIDIA GPU Requirements

**Hardware:**
- NVIDIA GPU with 16GB+ VRAM (recommended)
- CUDA Compute Capability 7.0+
- RTX 3090, A100, V100, or better

**Software:**
- CUDA 11.7+
- cuDNN 8.5+
- PyTorch 2.1+

**Installation:**

CUDA (Ubuntu/Debian):
```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-ubuntu2204.pin
sudo mv cuda-ubuntu2204.pin /etc/apt/preferences.d/cuda-repository-pin-600
sudo apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/3bf863cc.pub
sudo add-apt-repository "deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/ /"
sudo apt update
sudo apt install cuda
```

PyTorch with CUDA:
```bash
pip3 install --user torch>=2.1.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip3 install --user transformers accelerate bitsandbytes
```

Verify:
```bash
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python3 -c "import torch; print(f'GPU count: {torch.cuda.device_count()}')"
```

### Performance Optimization

**8-bit Quantization** (reduces VRAM by 50%):

In `app.py`, enable:
```python
from transformers import BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(
    load_in_8bit=True,
    llm_int8_threshold=6.0
)

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=quantization_config,
    device_map="auto"
)
```

**4-bit Quantization** (reduces VRAM by 75%):
```python
quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_quant_type="nf4"
)
```

**Batch Processing:**
```python
# Process multiple cases at once
batch_size = 4
responses = model.generate(
    input_ids,
    max_new_tokens=512,
    batch_size=batch_size
)
```

**Flash Attention 2** (2x faster):
```python
pip3 install flash-attn --no-build-isolation

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    attn_implementation="flash_attention_2"
)
```

**Multi-GPU:**
```python
# Automatic multi-GPU
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    device_map="auto"  # Distributes across all GPUs
)
```

## Environment Configuration

### Environment Variables

Create `.env` file:
```bash
FLASK_ENV=production
VECTA_PORT=8085
VECTA_HOST=0.0.0.0
DEBUG=False
MODEL_ID=m42-health/Llama3-Med42-8B
MAX_TOKENS=512
TEMPERATURE=0.7
```

Load in `app.py`:
```python
from dotenv import load_dotenv
load_dotenv()

port = int(os.getenv('VECTA_PORT', 8085))
host = os.getenv('VECTA_HOST', '0.0.0.0')
```

### Port Configuration

Default: 8085
Fallback range: 8085-8150

Override:
```bash
export VECTA_PORT=9000
./vecta start
```

Or in HPC:
```bash
./vecta-hpc run --port 9000
```

## Data Management

### Database Setup

SQLite database auto-created at `data/validation.db`

Initialize validation system:
```bash
python3 init_validation_system.py
```

Schema:
- `ai_outputs`: Stores AI responses for validation
- `neurologist_validations`: Expert reviews
- `validation_history`: Tracks improvements
- `demo_users`: Validator accounts

### Data Files

**Few-Shot Examples** (`few_shot_examples.py`):
- 50 neurology cases
- 10 conditions
- Expert-curated with citations
- 224KB

**Clinical Guidelines** (`clinical_guidelines.py`):
- ILAE 2025 Epilepsy Classification
- ICHD-3 Migraine Criteria
- AAN Guidelines
- AHA/ASA Stroke Guidelines
- MDS Parkinson's Criteria
- 72KB

**Sample Data** (`sample_medical_data.txt`):
- Neurology cases for testing
- EEG data examples
- MRI findings
- Patient registry data

### Backup

```bash
# Backup database
cp data/validation.db data/validation.db.backup

# Backup with timestamp
cp data/validation.db data/validation_$(date +%Y%m%d_%H%M%S).db

# Automated daily backup
0 2 * * * cd /opt/vecta && cp data/validation.db data/validation_$(date +\%Y\%m\%d).db
```

## System Requirements

### Minimum (Core Features)
- **CPU**: 2 cores
- **RAM**: 2GB
- **Storage**: 1GB
- **OS**: Linux, macOS, Windows
- **Python**: 3.8+
- **Network**: Internet for initial setup

### Recommended (Full AI Model)
- **CPU**: 8+ cores
- **RAM**: 32GB
- **GPU**: 16GB+ VRAM
- **Storage**: 20GB
- **CUDA**: 11.7+
- **Network**: High bandwidth for model download

### HPC Cluster
- **SLURM**: 20.11+
- **GPU**: V100, A100, or newer
- **Modules**: CUDA, Python, GCC
- **Network**: Infiniband (recommended)

## Security

### Production Checklist

- [ ] Change default credentials in `init_validation_system.py`
- [ ] Enable HTTPS (use Nginx with SSL)
- [ ] Set `DEBUG=False` in production
- [ ] Restrict access by IP/network
- [ ] Enable firewall (allow only 8085 or 443)
- [ ] Regular security updates
- [ ] Database encryption at rest
- [ ] Secure PHI according to HIPAA
- [ ] Regular backups
- [ ] Audit logging

### Firewall Configuration

```bash
# UFW (Ubuntu)
sudo ufw allow 8085/tcp
sudo ufw enable

# Firewalld (RHEL/CentOS)
sudo firewall-cmd --permanent --add-port=8085/tcp
sudo firewall-cmd --reload

# iptables
sudo iptables -A INPUT -p tcp --dport 8085 -j ACCEPT
```

### HIPAA Compliance

For PHI:
1. Use HTTPS only
2. Encrypt database
3. Audit all access
4. Implement role-based access control
5. Regular security assessments
6. Data retention policies
7. Secure backups

## Monitoring

### Application Health

Health check endpoint:
```bash
curl http://localhost:8085/health
```

Monitor logs:
```bash
# Local
./vecta logs

# HPC
./vecta-hpc logs -f

# Direct
tail -f vecta.log
```

### Performance Monitoring

GPU utilization:
```bash
watch -n 1 nvidia-smi
```

System resources:
```bash
htop
iostat 1
```

Network:
```bash
netstat -tulpn | grep 8085
ss -tulpn | grep 8085
```

### Validation System Stats

Access at: http://localhost:8085/validate

Metrics tracked:
- Total validations
- Agreement rate
- Cases pending review
- Neurologist activity

API endpoint:
```bash
curl http://localhost:8085/api/stats
```

## Troubleshooting

### Common Issues

**Port already in use:**
```bash
# Find process
lsof -ti:8085

# Kill process
kill -9 $(lsof -ti:8085)

# Or use different port
export VECTA_PORT=8086
./vecta start
```

**Module not found:**
```bash
# Reinstall dependencies
pip3 install --user flask flask-cors pandas numpy

# Or use requirements.txt
pip3 install --user -r requirements.txt
```

**PyTorch version error:**
```bash
# Upgrade PyTorch
pip3 install --user --upgrade "torch>=2.1.0"

# Or use CPU version
pip3 install --user torch torchvision torchaudio
```

**CUDA not available:**
```bash
# Check NVIDIA driver
nvidia-smi

# Verify CUDA
nvcc --version

# Reinstall PyTorch with CUDA
pip3 install --user torch --index-url https://download.pytorch.org/whl/cu118
```

**Database locked:**
```bash
# Close other connections
pkill -f "python.*app.py"

# Restart app
./vecta restart
```

**HPC job fails:**
```bash
# Check logs
./vecta-hpc logs

# Verify modules
module list

# Check job details
scontrol show job JOBID

# Request different resources
./vecta-hpc run --memory 128G
```

### Logs

**Local:**
- Application: `vecta.log`
- PID file: `vecta.pid`
- Location: Project root

**HPC:**
- Job output: `logs/vecta_JOBID.out`
- Job errors: `logs/vecta_JOBID.err`
- SLURM script: `slurm_job.sh`

### Getting Help

1. Check logs first
2. Verify system requirements
3. Review error messages
4. Check GitHub issues
5. Contact support

## Updates

### Updating Application

```bash
# Pull latest changes
git pull origin main

# Restart service
./vecta restart
```

### Updating Dependencies

```bash
# Update Python packages
pip3 install --user --upgrade flask flask-cors pandas numpy

# Update PyTorch
pip3 install --user --upgrade torch
```

### Database Migrations

```bash
# Backup first
cp data/validation.db data/validation.db.backup

# Run migrations (if provided)
python3 migrate_db.py
```

## Performance Benchmarks

### Response Times

**CPU Only:**
- Simple query: 2-5 seconds
- Complex analysis: 10-30 seconds

**With GPU (16GB):**
- Simple query: 0.5-1 second
- Complex analysis: 2-5 seconds

**With GPU (8-bit quantization):**
- Simple query: 0.3-0.7 seconds
- Complex analysis: 1-3 seconds

### Resource Usage

**CPU Mode:**
- RAM: 2-4GB
- CPU: 50-100%
- Storage: 1GB

**GPU Mode:**
- RAM: 8-16GB
- GPU VRAM: 12-16GB
- CPU: 20-40%
- Storage: 20GB

## Scaling

### Horizontal Scaling

Multiple instances with load balancer:
```bash
# Instance 1
./vecta start --port 8085

# Instance 2
./vecta start --port 8086

# Instance 3
./vecta start --port 8087

# Nginx load balancer
upstream vecta {
    server 127.0.0.1:8085;
    server 127.0.0.1:8086;
    server 127.0.0.1:8087;
}
```

### Vertical Scaling

Increase resources:
```bash
# HPC: More GPUs
./vecta-hpc run --gpus 4 --memory 256G

# Docker: More resources
docker run -d \
  --gpus all \
  --memory 64g \
  --cpus 16 \
  vecta-ai
```

## Cost Estimates

### Cloud GPU Pricing (Monthly)

**AWS:**
- P3.2xlarge (V100): ~$1,000
- G5.xlarge (A10G): ~$400

**Google Cloud:**
- A100 (40GB): ~$1,200
- T4: ~$300

**Azure:**
- NC6s v3 (V100): ~$900
- NCv3 (P100): ~$700

### HPC Cluster

Usually free or minimal cost through institutional access.

### Local Deployment

One-time hardware cost:
- RTX 3090 (24GB): ~$1,500
- RTX 4090 (24GB): ~$1,800
- A100 (40GB): ~$10,000

## Support

**Documentation:**
- README.md (Quick start)
- DEPLOYMENT.md (This file)

**Resources:**
- GitHub: https://github.com/phindagijimana/vecta
- Issues: https://github.com/phindagijimana/vecta/issues

**Community:**
- Report bugs via GitHub Issues
- Submit feature requests
- Contribute via pull requests

---

**Version**: 1.0  
**Last Updated**: 2026-02-13  
**Status**: Production Ready
