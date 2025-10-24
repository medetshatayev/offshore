# Deployment Checklist

## Pre-Deployment

### 1. Environment Setup
- [ ] Python 3.12+ installed
- [ ] Virtual environment created
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created with production values
- [ ] OpenAI API key configured and tested
- [ ] Temp storage path configured and writable

### 2. Configuration Review
- [ ] `OPENAI_API_KEY` set (never commit to git)
- [ ] `OPENAI_MODEL` appropriate for production (e.g., gpt-4o)
- [ ] `OPENAI_TIMEOUT` sufficient for expected load
- [ ] `TEMP_STORAGE_PATH` points to appropriate directory
- [ ] `LOG_LEVEL` set to INFO or WARNING (not DEBUG)
- [ ] `MAX_CONCURRENT_LLM_CALLS` tuned for API limits
- [ ] `AMOUNT_THRESHOLD_KZT` confirmed with stakeholders
- [ ] `HOST` and `PORT` appropriate for deployment environment

### 3. Security Verification
- [ ] `.env` file in `.gitignore`
- [ ] No hardcoded secrets in code
- [ ] PII redaction tested
- [ ] Account numbers properly masked in logs
- [ ] No sensitive data logged
- [ ] Temp files cleanup verified
- [ ] API key stored in secrets management (production)

### 4. Testing
- [ ] Setup verification script passes (`python verify_setup.py`)
- [ ] Sample Excel files processed successfully
- [ ] Output "Результат" column formatted correctly
- [ ] All classifications working (OFFSHORE_YES, SUSPECT, NO)
- [ ] Web search tool tested (if enabled)
- [ ] Error handling tested with invalid inputs
- [ ] Concurrent processing tested with multiple files
- [ ] Large file handling tested (500+ transactions)

### 5. Documentation
- [ ] README.md reviewed and accurate
- [ ] QUICKSTART.md tested by new user
- [ ] Internal documentation updated
- [ ] API endpoints documented
- [ ] Error codes and messages documented
- [ ] Contact information for support updated

## Deployment Steps

### Option A: Local Server

1. **Prepare environment**:
   ```bash
   cd offshore_risk
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure**:
   ```bash
   cp .env.example .env
   # Edit .env with production values
   ```

3. **Verify**:
   ```bash
   python verify_setup.py
   ```

4. **Start server**:
   ```bash
   python main.py
   ```

5. **Test**:
   - Access http://localhost:8000
   - Upload test files
   - Verify outputs

### Option B: Docker (Recommended for Production)

1. **Create Dockerfile**:
   ```dockerfile
   FROM python:3.12-slim
   
   WORKDIR /app
   
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   
   COPY . .
   
   EXPOSE 8000
   
   CMD ["python", "main.py"]
   ```

2. **Build image**:
   ```bash
   docker build -t offshore-risk:1.0.0 .
   ```

3. **Run container**:
   ```bash
   docker run -d \
     --name offshore-risk \
     -p 8000:8000 \
     -e OPENAI_API_KEY=your_key_here \
     -v /path/to/storage:/tmp/offshore_risk \
     offshore-risk:1.0.0
   ```

4. **Verify**:
   ```bash
   docker logs offshore-risk
   curl http://localhost:8000/health
   ```

### Option C: Systemd Service (Linux)

1. **Create service file** (`/etc/systemd/system/offshore-risk.service`):
   ```ini
   [Unit]
   Description=Offshore Transaction Risk Detection
   After=network.target
   
   [Service]
   Type=simple
   User=offshore
   WorkingDirectory=/opt/offshore_risk
   Environment="PATH=/opt/offshore_risk/venv/bin"
   ExecStart=/opt/offshore_risk/venv/bin/python main.py
   Restart=always
   RestartSec=10
   
   [Install]
   WantedBy=multi-user.target
   ```

2. **Enable and start**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable offshore-risk
   sudo systemctl start offshore-risk
   sudo systemctl status offshore-risk
   ```

## Post-Deployment

### 1. Smoke Testing
- [ ] Health check endpoint responds: `GET /health`
- [ ] Web interface loads: `GET /`
- [ ] File upload works with small test file
- [ ] Download link works
- [ ] Logs are being written correctly
- [ ] No errors in startup logs

### 2. Monitoring Setup
- [ ] Health check endpoint monitored (every 1 minute)
- [ ] Log aggregation configured (if applicable)
- [ ] Disk space monitoring (temp storage)
- [ ] API usage monitoring (OpenAI quotas)
- [ ] Error rate alerting configured
- [ ] Response time monitoring

### 3. Operational Procedures
- [ ] Backup procedures documented
- [ ] Log rotation configured
- [ ] Restart procedures documented
- [ ] Upgrade procedures documented
- [ ] Rollback procedures documented
- [ ] Incident response plan in place

### 4. User Training
- [ ] End users trained on web interface
- [ ] File format requirements communicated
- [ ] Expected processing times documented
- [ ] Error messages and solutions documented
- [ ] Support contact information provided

## Production Checklist

### Performance
- [ ] `MAX_CONCURRENT_LLM_CALLS` optimized
- [ ] Timeout values appropriate
- [ ] Memory limits configured
- [ ] Disk space sufficient
- [ ] Network connectivity verified

### Security
- [ ] HTTPS enabled (reverse proxy recommended)
- [ ] Authentication/authorization implemented (if needed)
- [ ] API key in secrets management
- [ ] Firewall rules configured
- [ ] Access logs enabled
- [ ] No debug mode in production

### Reliability
- [ ] Process supervisor configured (systemd/supervisord)
- [ ] Auto-restart on failure
- [ ] Health checks monitored
- [ ] Backup API key available
- [ ] Failover procedures documented

### Compliance
- [ ] Data retention policy implemented
- [ ] PII handling verified
- [ ] Audit logging enabled
- [ ] Access controls documented
- [ ] Compliance requirements met

## Rollback Plan

If issues occur after deployment:

1. **Immediate**: Stop the service
   ```bash
   # Systemd
   sudo systemctl stop offshore-risk
   
   # Docker
   docker stop offshore-risk
   
   # Manual
   pkill -f "python main.py"
   ```

2. **Restore previous version**:
   - Git: `git checkout <previous-tag>`
   - Docker: `docker run offshore-risk:<previous-version>`
   - Files: Restore from backup

3. **Verify rollback**:
   - Check logs
   - Test with sample file
   - Verify outputs

4. **Document issue**:
   - What went wrong?
   - Why rollback was needed?
   - What needs to be fixed?

## Troubleshooting

### Service won't start
- Check logs: `journalctl -u offshore-risk -n 100`
- Verify .env file exists and is readable
- Check Python version: `python --version`
- Verify all dependencies: `pip list`

### Files not processing
- Check OpenAI API key is valid
- Verify API quotas not exceeded
- Check temp storage is writable
- Review application logs

### Slow performance
- Reduce `MAX_CONCURRENT_LLM_CALLS`
- Check network latency to OpenAI
- Monitor server resources (CPU, RAM)
- Consider batching smaller files

### Out of disk space
- Check `TEMP_STORAGE_PATH` usage
- Implement cleanup cron job
- Adjust log rotation
- Monitor disk usage

## Maintenance

### Regular Tasks
- **Daily**: Check error logs
- **Weekly**: Review API usage and costs
- **Monthly**: Update dependencies (security patches)
- **Quarterly**: Performance review and optimization

### Updates
1. Test in staging environment first
2. Backup current version
3. Deploy during low-usage window
4. Monitor for issues
5. Keep previous version ready for rollback

## Support Contacts

- **Technical Support**: [Insert contact]
- **API Issues (OpenAI)**: platform.openai.com/support
- **Emergency Contact**: [Insert contact]
- **Documentation**: /workspace/offshore_risk/README.md

---

**Deployment Date**: __________  
**Deployed By**: __________  
**Version**: 1.0.0  
**Environment**: __________  
**Sign-off**: __________
