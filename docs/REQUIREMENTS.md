# GitHub Commit Tracking Automation - Requirements Document

## 1. Project Overview

**Purpose**: Automate the monthly collection and reporting of GitHub commits across specified repositories.

**Current Process**: Manual review of GitHub repositories, data extraction, Google Sheets creation, and email distribution.

**Desired Outcome**: Fully automated monthly report generation and delivery.

## 2. Functional Requirements

### 2.1 Data Collection
- **Source**: GitHub repositories (public/private as specified)
- **Repositories to Monitor**: 
  - Repository X: `[organization/repo-name-x]`
  - Repository Y: `[organization/repo-name-y]`
  - Repository Z: `[organization/repo-name-z]`
  - *Note: Replace with actual repository URLs/names*
- **Data Scope**: All commits within the specified month
- **Default Behavior**: Current month's commits (if run mid-month or at month-end)
- **Flexible Date Range**: Ability to specify custom month/year when needed

### 2.2 Data Points to Capture
For each commit, collect:
1. **Serial Number**: Sequential numbering (1, 2, 3...)
2. **Commit Hash**: Full SHA hash
3. **Commit URL**: Direct link to the commit on GitHub
4. **Commit Message**: Full commit message text
5. **Date & Time**: Commit timestamp (formatted as YYYY-MM-DD HH:MM:SS)
6. **Username**: GitHub username of the committer
7. **Repository Name**: Name of the repository
8. **AI Summary**: Claude-generated summary of code changes (see Section 2.7)
9. **Change Type**: AI-categorized type of change (Feature, Bug Fix, Refactor, etc.)

### 2.3 Output Generation
- **Format**: Google Sheets spreadsheet
- **Sheet Name**: "GitHub Commits - [Month Year]" (e.g., "GitHub Commits - March 2024")
- **Column Headers**:
  - Column A: No.
  - Column B: Commit Hash
  - Column C: URL
  - Column D: Commit Message
  - Column E: Date Time
  - Column F: Username
  - Column G: Repo Name
  - Column H: AI Summary
  - Column I: Change Type

### 2.4 Data Organization
- **Sorting**: Chronological order (oldest to newest)
- **Grouping**: Optional grouping by repository with clear visual separation
- **Formatting**: Professional appearance with header row formatting

### 2.5 Delivery
- **Method**: Email with Google Sheets attachment or shareable link
- **Recipient**: recipient@example.com
- **Subject Line**: "Monthly GitHub Commit Report with AI Analysis - [Month Year]"
- **Email Body**: Brief summary including:
  - Total number of commits
  - Number of repositories processed
  - Date range covered
  - AI analysis statistics (commits processed, categorization breakdown)
  - Any notable observations or issues

### 2.6 Data Organization
- **Sorting**: Chronological order (oldest to newest)
- **Grouping**: Optional grouping by repository with clear visual separation
- **Formatting**: Professional appearance with header row formatting
- **AI Summary Formatting**: Proper text wrapping and cell sizing for readability

### 2.7 AI-Powered Code Analysis Feature

#### 2.7.1 Integration Overview
- **AI Service**: Claude API integration for intelligent commit analysis
- **Purpose**: Provide human-readable summaries of technical code changes
- **Scope**: Process all commits captured in the monthly report

#### 2.7.2 Code Diff Analysis
- **Data Source**: GitHub API commit diff data
- **Supported File Types**: 
  - Programming languages (.js, .py, .java, .go, .php, .rb, .cs, etc.)
  - Configuration files (.json, .yaml, .xml, .env, etc.)
  - Documentation files (.md, .txt, .rst, etc.)
  - Database scripts (.sql)
- **Diff Processing**: Extract added, modified, and deleted lines for analysis

#### 2.7.3 AI Summary Generation
- **Summary Length**: 50-150 words per commit
- **Summary Content**: Should include:
  - **What was changed**: Brief description of modified components
  - **Why it was changed**: Inferred purpose based on code patterns
  - **Impact assessment**: Potential effects on functionality
  - **Technical details**: Key methods/functions/classes affected

**Example AI Summary Format**:
```
"Modified user authentication system by adding two-factor authentication support. Updated login controller to include SMS verification step and added new database table for storing verification codes. Enhanced security middleware to validate 2FA tokens. This change improves account security but may require users to update their login process."
```

#### 2.7.4 Change Categorization
AI should categorize each commit into one of these types:
- **Feature**: New functionality or capability
- **Bug Fix**: Correcting existing issues
- **Refactor**: Code restructuring without changing functionality
- **Performance**: Optimization improvements
- **Security**: Security-related changes
- **Documentation**: Documentation updates
- **Configuration**: Config/setup changes
- **Dependencies**: Library or package updates
- **Database**: Database schema or migration changes
- **UI/UX**: User interface improvements
- **Test**: Testing-related changes
- **Build/Deploy**: Build system or deployment changes
- **Other**: Miscellaneous changes

#### 2.7.5 AI Processing Workflow
1. **Fetch Commit Data**: Retrieve commit details and diff from GitHub API
2. **Code Diff Extraction**: Parse file changes and extract meaningful code segments
3. **Context Preparation**: Prepare code context for Claude API
4. **AI Analysis Request**: Send structured prompt to Claude API
5. **Response Processing**: Parse AI response for summary and categorization
6. **Quality Validation**: Ensure response meets format requirements
7. **Data Integration**: Combine AI insights with commit metadata

#### 2.7.6 Claude API Integration Specifications
- **API Endpoint**: Anthropic Claude API (latest available model)
- **Model Recommendation**: Claude Sonnet 4 for balance of speed and quality
- **Request Format**: Structured prompts with code diff context
- **Rate Limiting**: Implement proper rate limiting (max 50 requests/minute)
- **Retry Logic**: Handle API failures with exponential backoff
- **Cost Management**: Token usage monitoring and optimization

#### 2.7.7 AI Prompt Template
```
Analyze this GitHub commit and provide:
1. A concise summary (50-150 words) of what was changed and why
2. Categorize the change type from: [Feature, Bug Fix, Refactor, Performance, Security, Documentation, Configuration, Dependencies, Database, UI/UX, Test, Build/Deploy, Other]

Commit Message: {commit_message}
Repository: {repo_name}
Files Changed: {file_list}
Code Diff: {code_diff}

Focus on business impact and technical significance. Be specific about what functionality was added, modified, or removed.
```

#### 2.7.8 Error Handling for AI Features
- **API Unavailable**: Graceful degradation - continue without AI analysis
- **Token Limits**: Truncate large diffs intelligently, prioritize core changes
- **Analysis Failures**: Mark commits as "Analysis Failed" with reason
- **Quality Issues**: Validate AI responses for completeness and relevance
- **Fallback Strategy**: Use commit message analysis if code diff analysis fails

## 3. Technical Requirements

### 3.1 APIs and Integrations
- **GitHub API**: Access to repository commit data and diff information
- **Claude API**: Anthropic's Claude API for AI-powered code analysis
- **Google Sheets API**: Spreadsheet creation and formatting
- **Email Service**: Gmail/SMTP or similar for email delivery

### 3.2 Authentication
- **GitHub**: Personal Access Token or GitHub App credentials
- **Claude API**: Anthropic API key with appropriate usage limits
- **Google Sheets**: Service account or OAuth2 credentials
- **Email**: SMTP credentials or Gmail API access

### 3.3 Scheduling
- **Primary Schedule**: Last day of each month at 11:59 PM
- **Backup Schedule**: First day of following month at 9:00 AM (if primary fails)
- **Manual Trigger**: Ability to run on-demand for specific date ranges
- **AI Processing**: Account for additional processing time due to AI analysis (estimated 2-5 minutes per commit)

### 3.4 Error Handling
- **API Rate Limits**: Implement proper rate limiting and retry logic for GitHub and Claude APIs
- **Network Issues**: Retry mechanisms with exponential backoff
- **Authentication Failures**: Clear error messages and notification
- **Data Validation**: Verify data completeness before processing
- **AI Analysis Failures**: Graceful degradation when AI analysis is unavailable
- **Token Usage**: Monitor Claude API token consumption and implement usage limits
- **Notification**: Email notification if script fails with error details

## 4. Configuration Requirements

### 4.1 Configurable Parameters
- Repository list (easy to add/remove repositories)
- Email recipient(s)
- Date range override
- Output format preferences
- Scheduling frequency
- **AI Analysis Settings**:
  - Enable/disable AI analysis per repository
  - Claude model selection (Sonnet 4, Opus 4)
  - Summary length preferences
  - Custom categorization rules
  - Token usage limits

### 4.2 Environment Variables
- GitHub token
- Claude API key
- Google Sheets credentials
- Email service credentials
- Recipient email address
- AI analysis configuration flags

## 5. Security Requirements

### 5.1 Credential Management
- Secure storage of API tokens and credentials
- No hardcoded sensitive information in scripts
- Use of environment variables or secure vault systems

### 5.2 Access Control
- Minimum required permissions for GitHub access
- Read-only access where possible
- Secure handling of generated spreadsheets

## 6. Performance Requirements

### 6.1 Execution Time
- Complete execution within 60 minutes for typical monthly data (increased from 30 minutes due to AI processing)
- Efficient API usage to avoid rate limiting across multiple services
- Batch processing for large datasets
- Parallel processing where possible for AI analysis

### 6.2 Resource Usage
- Minimal server resource consumption
- Efficient memory usage for large commit datasets
- **AI Processing Considerations**:
  - Token usage optimization for Claude API
  - Intelligent diff truncation for large commits
  - Caching of AI responses to avoid reprocessing
  - Cost monitoring and budget controls

## 7. Monitoring and Logging

### 7.1 Logging Requirements
- Execution start/end times
- Number of commits processed per repository
- API calls made and rate limit status for all services (GitHub, Claude, Google Sheets)
- AI analysis success/failure rates
- Token usage statistics for Claude API
- Cost tracking for AI services
- Error occurrences and resolution attempts

### 7.2 Success Confirmation
- Email confirmation when report is successfully generated and sent
- Summary statistics in the confirmation email including:
  - Total commits processed
  - AI analysis completion rate
  - Categorization breakdown
  - Token usage summary
  - Processing time metrics

## 8. Testing Requirements

### 8.1 Unit Testing
- Individual function testing for data extraction, formatting, and delivery
- Mock API responses for testing edge cases

### 8.2 Integration Testing
- End-to-end testing with actual GitHub repositories
- Google Sheets creation and formatting verification
- Email delivery confirmation

### 8.3 Edge Case Testing
- Empty repositories (no commits)
- Repositories with large numbers of commits
- Very large commit diffs (>10MB)
- Binary file changes (images, executables)
- Merge commits with complex diffs
- Claude API rate limiting and failures
- Network connectivity issues
- Mixed programming languages in single commit
- Commits with no meaningful code changes
- AI analysis timeout scenarios

## 9. Deployment Requirements

### 9.1 Hosting Options
- Cloud function (AWS Lambda, Google Cloud Functions, etc.)
- Scheduled job on cloud platform
- Local server with cron job
- GitHub Actions workflow

### 9.2 Backup and Recovery
- Script backup and version control
- Configuration backup
- Recovery procedures for failed executions

## 10. Maintenance and Updates

### 10.1 Regular Maintenance
- Monthly review of script performance
- Quarterly security review of credentials
- Annual review of repository list and requirements

### 10.2 Future Enhancements
- Web dashboard for viewing historical reports
- Additional output formats (PDF, CSV)
- Advanced filtering and search capabilities
- Integration with project management tools
- **AI-Powered Enhancements**:
  - Trend analysis across multiple months
  - Developer productivity insights
  - Code complexity scoring
  - Risk assessment for changes
  - Automated code review suggestions
  - Integration with other AI models for specialized analysis
  - Custom AI prompts for specific project types

## 11. Success Criteria

### 11.1 Primary Success Metrics
- 100% successful monthly report generation
- Zero manual intervention required
- Reports delivered within 24 hours of month-end
- Complete and accurate data capture
- **AI Analysis Metrics**:
  - >95% successful AI analysis completion rate
  - <10% "Analysis Failed" entries per report
  - Meaningful and accurate summaries for >90% of commits

### 11.2 Quality Metrics
- Data accuracy: 99.9% of commits captured correctly
- Delivery reliability: 99% successful email delivery
- Processing time: Under 60 minutes for monthly data (including AI analysis)
- **AI Quality Metrics**:
  - Summary relevance score: >8/10 based on sample review
  - Categorization accuracy: >90% correct classification
  - Cost efficiency: <$X per month in Claude API usage (define budget)

## 12. Timeline and Milestones

### Phase 1: Development (Weeks 1-3)
- API integration setup (GitHub, Claude, Google Sheets)
- Core data extraction logic
- AI analysis implementation and prompt engineering
- Basic Google Sheets generation with new columns

### Phase 2: Integration & Testing (Weeks 4-5)
- Email delivery implementation
- Error handling and logging
- AI analysis testing and optimization
- Performance testing with large datasets

### Phase 3: Deployment (Week 6)
- Production deployment
- Scheduling setup
- Cost monitoring implementation
- Documentation and handover

## 13. Support and Documentation

### 13.1 Documentation Deliverables
- Technical documentation for the script
- Configuration guide (including AI settings)
- Troubleshooting guide
- User manual for manual execution
- **AI-Specific Documentation**:
  - Claude API integration guide
  - Prompt customization instructions
  - Cost monitoring and optimization guide
  - AI analysis quality assessment procedures

### 13.2 Support Requirements
- Initial 30-day support period
- Knowledge transfer session
- Contact information for ongoing support

---

## 14. AI Feature Cost Considerations

### 14.1 Cost Estimation
- **Claude API Pricing**: Based on token usage (input + output tokens)
- **Estimated Monthly Cost**: 
  - Small repos (50-100 commits/month): $5-15
  - Medium repos (200-500 commits/month): $20-50
  - Large repos (1000+ commits/month): $75-150
- **Cost Variables**: 
  - Number of commits
  - Size of code diffs
  - Complexity of changes
  - Model selection (Sonnet vs Opus)

### 14.2 Cost Optimization Strategies
- **Intelligent Diff Filtering**: Skip trivial changes (whitespace, comments only)
- **Batch Processing**: Group similar commits for analysis
- **Caching**: Store and reuse analysis for identical diffs
- **Selective Analysis**: Focus on critical repositories or file types
- **Model Selection**: Use appropriate Claude model based on complexity

### 14.3 Budget Controls
- **Monthly Spending Limits**: Configurable API usage caps
- **Alert Thresholds**: Notifications when approaching budget limits
- **Graceful Degradation**: Disable AI analysis if budget exceeded
- **Usage Reporting**: Monthly cost breakdown and trends

---

**Document Version**: 2.0 (AI-Enhanced)  
**Last Updated**: [Current Date]  
**Prepared By**: [Your Name]  
**Approved By**: [Approval Required]

---

## Additional Notes for AI Integration

**Benefits of AI Analysis:**
- **Enhanced Insights**: Understand the business impact of technical changes
- **Better Categorization**: Automatically classify commits by type and impact
- **Non-Technical Summaries**: Make technical changes understandable for management
- **Pattern Detection**: Identify common types of changes and potential issues
- **Time Saving**: Eliminate manual review of code changes

**Implementation Considerations:**
- Start with a pilot implementation on 1-2 repositories
- Monitor AI analysis quality and adjust prompts as needed
- Implement cost controls from day one
- Plan for API failures and graceful degradation
- Consider data privacy implications of sending code to external AI service