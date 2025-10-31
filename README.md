# AIS Job Alert Webhook

Automated job posting monitor that tracks GitHub repositories for new internship and new grad opportunities and sends real-time notifications to Discord.

## Features

- **Automated Monitoring**: Checks for new jobs every 3 hours using GitHub Actions
- **Multi-Repository Support**: Monitors both Summer 2026 Internships and New Grad 2026 positions
- **Smart Deduplication**: Uses hash-based job identification to prevent duplicate notifications
- **Rich Discord Notifications**: Beautiful embed messages with company, role, location, and direct application links
- **Job Status Detection**: Automatically filters out closed positions and identifies visa sponsorship requirements
- **Zero Cost**: Runs completely free on GitHub Actions (no server needed)

## Monitored Repositories

1. [Summer 2026 Internships](https://github.com/vanshb03/Summer2026-Internships)
2. [New Grad 2026](https://github.com/vanshb03/New-Grad-2026)

## How It Works

1. **Fetch**: Downloads README.md files from target GitHub repositories
2. **Parse**: Extracts job data from markdown tables (Company, Role, Location, Application Link)
3. **Compare**: Checks against cached jobs to identify new postings
4. **Notify**: Sends Discord webhook notifications for new jobs
5. **Cache**: Updates `job_cache.json` to prevent duplicate alerts

## Setup Instructions

### Prerequisites

- GitHub account
- Discord webhook URL (already configured in `config.json`)

### Local Testing (Optional)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ais-job-alert-webhook.git
   cd ais-job-alert-webhook
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the bot manually**:
   ```bash
   python bot.py
   ```

   This will:
   - Fetch current job listings from both repositories
   - Display found jobs in the console
   - Send Discord notifications for new jobs
   - Update `job_cache.json`

### Deployment to GitHub Actions

1. **Create a new GitHub repository**:
   - Go to [GitHub](https://github.com/new)
   - Name: `ais-job-alert-webhook` (or your preferred name)
   - Visibility: Private or Public (your choice)
   - Click "Create repository"

2. **Push the code to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Job alert webhook bot"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/ais-job-alert-webhook.git
   git push -u origin main
   ```

3. **Enable GitHub Actions**:
   - Go to your repository on GitHub
   - Click on the "Actions" tab
   - If prompted, click "I understand my workflows, go ahead and enable them"
   - GitHub Actions will now run automatically every 3 hours

4. **Verify the workflow**:
   - Go to Actions tab
   - You should see "Job Alert Checker" workflow
   - Click "Run workflow" button to trigger a manual test run
   - Check the logs to ensure it runs successfully

5. **Check your Discord channel**:
   - New job postings will appear as rich embeds
   - Blue embeds (🎓) = Internships
   - Green embeds (💼) = New Grad positions

## Configuration

### config.json

The `config.json` file contains all configuration settings:

```json
{
  "discord_webhook_url": "YOUR_WEBHOOK_URL",
  "repositories": [
    {
      "name": "Summer 2026 Internships",
      "url": "https://github.com/vanshb03/Summer2026-Internships",
      "type": "Internship",
      "badge": "🎓",
      "color": "#3447eb"
    }
  ],
  "check_interval_hours": 3
}
```

**To modify**:
- `discord_webhook_url`: Your Discord webhook URL
- `repositories`: Add/remove repositories to monitor
- `check_interval_hours`: Change monitoring frequency (update `.github/workflows/job-checker.yml` cron schedule accordingly)

### Changing Check Frequency

To modify the 3-hour check interval:

1. Edit `.github/workflows/job-checker.yml`
2. Change the cron expression:
   ```yaml
   schedule:
     - cron: '0 */3 * * *'  # Every 3 hours
   ```

   Common cron patterns:
   - `0 */6 * * *` - Every 6 hours
   - `0 9,17 * * *` - Twice daily (9 AM and 5 PM UTC)
   - `0 * * * *` - Every hour

3. Commit and push the changes

## File Structure

```
ais-job-alert-webhook/
├── bot.py                      # Main bot script
├── config.json                 # Configuration file
├── requirements.txt            # Python dependencies
├── job_cache.json             # Cached job IDs (auto-generated)
├── .gitignore                 # Git ignore rules
├── README.md                  # This file
└── .github/
    └── workflows/
        └── job-checker.yml    # GitHub Actions workflow
```

## Troubleshooting

### No notifications appearing in Discord

1. **Check workflow logs**:
   - Go to Actions tab in your repository
   - Click on the latest workflow run
   - Review the logs for errors

2. **Verify webhook URL**:
   - Test your Discord webhook manually:
     ```bash
     curl -X POST YOUR_WEBHOOK_URL \
       -H "Content-Type: application/json" \
       -d '{"content": "Test message"}'
     ```

3. **Check cache**:
   - The first run will mark all existing jobs as "seen"
   - New notifications only appear for jobs posted *after* the first run
   - To reset: delete `job_cache.json` and commit the change

### GitHub Actions not running

1. **Check if Actions are enabled**:
   - Go to Settings → Actions → General
   - Ensure "Allow all actions and reusable workflows" is selected

2. **Verify permissions**:
   - Go to Settings → Actions → General → Workflow permissions
   - Select "Read and write permissions"
   - Check "Allow GitHub Actions to create and approve pull requests"

### Bot runs but finds no new jobs

- This is normal if no new jobs have been posted since the last check
- Check the logs to see how many jobs were parsed vs cached
- Manually compare with the GitHub repositories to verify

### Rate limiting issues

- GitHub API allows 60 requests/hour for unauthenticated requests
- The bot makes 2 requests per run (one per repository)
- Running every 3 hours = 16 requests/day (well within limits)

## Manual Workflow Trigger

You can manually trigger the job checker:

1. Go to Actions tab in your repository
2. Click "Job Alert Checker" workflow
3. Click "Run workflow" button
4. Select branch (main)
5. Click "Run workflow"

This is useful for:
- Testing after configuration changes
- Forcing an immediate check
- Debugging issues

## Maintenance

### Updating Dependencies

```bash
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt
git add requirements.txt
git commit -m "Update dependencies"
git push
```

### Adding New Repositories

1. Edit `config.json`
2. Add new repository to the `repositories` array:
   ```json
   {
     "name": "New Repo Name",
     "url": "https://github.com/user/repo",
     "type": "Job Type",
     "badge": "🎯",
     "color": "#ff5733"
   }
   ```
3. Commit and push changes

### Viewing Cache

To see what jobs have been tracked:

```bash
cat job_cache.json | python -m json.tool
```

## Security Notes

- **Webhook URL**: Keep your Discord webhook URL private
- **Repository Visibility**: If your repo is public, consider using GitHub Secrets for the webhook URL
- **API Tokens**: No GitHub API token required for public repositories

## Advanced: Using GitHub Secrets (Optional)

For additional security, store the webhook URL in GitHub Secrets:

1. Go to Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `DISCORD_WEBHOOK_URL`
4. Value: Your webhook URL
5. Modify `bot.py` to read from environment variable:
   ```python
   import os
   webhook_url = os.environ.get('DISCORD_WEBHOOK_URL', config['discord_webhook_url'])
   ```
6. Update workflow to pass the secret:
   ```yaml
   - name: Run job checker bot
     env:
       DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
     run: python bot.py
   ```

## License

MIT License - feel free to modify and use for your own purposes.

## Credits

- Job listings sourced from:
  - [vanshb03/Summer2026-Internships](https://github.com/vanshb03/Summer2026-Internships)
  - [vanshb03/New-Grad-2026](https://github.com/vanshb03/New-Grad-2026)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review workflow logs in GitHub Actions
3. Test the bot locally with `python bot.py`
4. Verify configuration in `config.json`

---

**Happy job hunting!** 🎓💼