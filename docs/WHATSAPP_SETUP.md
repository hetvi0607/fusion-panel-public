# WhatsApp Business API Setup Guide

This guide will help you set up WhatsApp Business API integration to send commit reports and AI summaries to WhatsApp groups.

## Table of Contents
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Step-by-Step Setup](#step-by-step-setup)
- [Configuration](#configuration)
- [Getting Group IDs](#getting-group-ids)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [API Limits](#api-limits)

## Overview

The WhatsApp integration uses **Meta's WhatsApp Business Cloud API** to:
- Send AI-generated summaries as formatted text messages
- Send CSV reports as document attachments
- Support multiple recipient groups
- Provide delivery status tracking

## Prerequisites

1. **WhatsApp Business Account** - You need a verified WhatsApp Business account
2. **Meta Business Account** - A Meta (Facebook) Business account
3. **Meta Developer Account** - Access to Meta for Developers
4. **Phone Number** - A phone number to register with WhatsApp Business (cannot be already registered with WhatsApp)

## Step-by-Step Setup

### 1. Create a Meta App

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Click **"My Apps"** → **"Create App"**
3. Select **"Business"** as the app type
4. Fill in app details:
   - **App Name**: e.g., "GitHub Commit Reporter"
   - **App Contact Email**: Your email
   - **Business Account**: Select or create a business account
5. Click **"Create App"**

### 2. Add WhatsApp Product

1. In your app dashboard, find **"WhatsApp"** in the product list
2. Click **"Set up"** on WhatsApp
3. This will add WhatsApp to your app

### 3. Configure WhatsApp Business API

1. In the WhatsApp section, you'll see:
   - **Test number** (provided by Meta for testing)
   - **Production number** (your own number to register)

#### For Testing (Recommended First):
1. Use Meta's test number
2. Add up to 5 recipient numbers in the test recipients list
3. Send a test message from the API dashboard to verify setup

#### For Production:
1. Click **"Add Phone Number"**
2. Verify your business phone number
3. Complete the verification process (SMS or call)
4. Once verified, you can send messages to any number

### 4. Get Required Credentials

You need three key pieces of information:

#### A. Access Token
1. In WhatsApp → **Getting Started**
2. Find the **"Temporary access token"** (valid for 24 hours)
3. **For production**, generate a **permanent access token**:
   - Go to **Business Settings** → **System Users**
   - Create a system user
   - Assign it to your app
   - Generate a permanent token with `whatsapp_business_messaging` permission

#### B. Phone Number ID
1. In WhatsApp → **Getting Started** or **API Setup**
2. Look for **"Phone Number ID"** (starts with numbers)
3. Copy this ID

#### C. Business Account ID
1. In WhatsApp → **Getting Started**
2. Find **"WhatsApp Business Account ID"**
3. Copy this ID

### 5. Update Environment Variables

Edit your `.env` file and add:

```bash
# WhatsApp Business API settings
WHATSAPP_ENABLED=True
WHATSAPP_ACCESS_TOKEN=your_permanent_access_token_here
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_BUSINESS_ACCOUNT_ID=123456789012345
WHATSAPP_GROUP_IDS=YOUR_RECIPIENT_ID
```

**Important Notes:**
- Phone numbers should be in international format **without** the `+` sign
- For India: `919876543210` (91 is country code)
- For US: `11234567890` (1 is country code)
- For groups, you'll need the group ID (see next section)

## Getting Group IDs

WhatsApp Business API handles groups differently:

### Method 1: Using WhatsApp Business Manager
1. Go to [WhatsApp Business Manager](https://business.facebook.com/wa/manage/home/)
2. Navigate to **Message Templates** → **Analytics**
3. You can find group IDs in the recipient lists

### Method 2: Webhook Method
1. Set up a webhook in your Meta app
2. When someone sends a message to your business number from a group, the webhook will receive the group ID
3. You can log this ID for future use

### Method 3: Direct Messaging (Recommended for Testing)
For initial testing, use individual phone numbers instead of groups:
```bash
WHATSAPP_GROUP_IDS=YOUR_RECIPIENT_ID
```

**Note:** The recipient must have messaged your WhatsApp Business number first (or be in your test recipients list) before you can send them messages.

## Configuration

### Environment Variables

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `WHATSAPP_ENABLED` | Enable/disable WhatsApp integration | Yes | `True` or `False` |
| `WHATSAPP_ACCESS_TOKEN` | Meta access token | Yes | `EAAxxxx...` |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp phone number ID | Yes | `123456789012345` |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | Business account ID | No | `123456789012345` |
| `WHATSAPP_GROUP_IDS` | Comma-separated recipient IDs | Yes | `YOUR_RECIPIENT_ID` |

### Message Format

The integration sends:
1. **AI Summary** - Formatted text message with repository summaries
2. **CSV Report** - Document attachment with full commit data

Messages are automatically:
- Formatted for WhatsApp (markdown-style)
- Truncated if longer than 4096 characters
- Sent with appropriate error handling

## Testing

### 1. Test with Sample Number

```bash
# In .env
WHATSAPP_ENABLED=True
WHATSAPP_ACCESS_TOKEN=your_test_token
WHATSAPP_PHONE_NUMBER_ID=test_phone_id
WHATSAPP_GROUP_IDS=your_test_number
```

### 2. Run the Script

```bash
python main.py --month 2024-11
```

### 3. Verify Messages

Check your WhatsApp (or test recipient's WhatsApp) for:
- Text message with AI summary
- CSV file attachment

## Troubleshooting

### Common Issues

#### 1. "Access Token is Invalid"
- **Cause**: Token expired or incorrect
- **Solution**: Generate a new permanent token from Business Settings

#### 2. "Phone Number Not Registered"
- **Cause**: Phone number not verified with WhatsApp Business
- **Solution**: Complete phone number verification in Meta dashboard

#### 3. "Recipient Not Found" or "Message Not Sent"
- **Cause**: Recipient hasn't initiated conversation
- **Solution**: 
  - For testing: Add recipient to test recipients list
  - For production: Recipient must message your business number first, or you must use approved message templates

#### 4. "Rate Limit Exceeded"
- **Cause**: Too many messages sent too quickly
- **Solution**: Wait and retry. Check rate limits below.

#### 5. "Media Upload Failed"
- **Cause**: File too large or invalid format
- **Solution**: 
  - CSV files should be under 100MB
  - Ensure file exists and is readable

### Debug Mode

Enable verbose logging to see detailed API responses:

```bash
python main.py --verbose --month 2024-11
```

Check `commit_tracker.log` for detailed error messages.

## API Limits

### Free Tier (Cloud API - Test Mode)
- **Messages per day**: 1,000 messages
- **Message templates**: Limited to test recipients only
- **Supported recipients**: Up to 5 test numbers

### Paid Tier (Cloud API - Production)
- **Messages per day**: Based on your tier (starts at 1,000, can scale)
- **Conversation pricing**: Conversations are charged based on category
- **Rate limits**: 
  - 80 messages per second per phone number
  - 20 requests per second per business

### File Size Limits
- **Documents (CSV)**: Max 100MB
- **Images**: Max 5MB
- **Audio**: Max 16MB

### Message Limits
- **Text message**: 4096 characters
- **Caption**: 1024 characters

## Best Practices

1. **Use Permanent Tokens**: Don't use temporary tokens in production
2. **Store Tokens Securely**: Never commit tokens to Git
3. **Handle Errors Gracefully**: The integration will log errors but continue execution
4. **Test First**: Always test with test recipients before production
5. **Monitor Costs**: Check your Meta Business Manager for conversation costs
6. **Rate Limiting**: Avoid sending too many messages in quick succession

## Message Templates (Optional)

For sending messages to users who haven't messaged you first, you need to use **Message Templates**:

1. Go to **WhatsApp** → **Message Templates**
2. Create a template (requires approval from Meta)
3. Use the template in your code with the template API

**Note**: The current implementation uses direct messaging, which works for:
- Users who have messaged your business number
- Test recipients
- Groups where your business number is a member

## Additional Resources

- [WhatsApp Business Platform Documentation](https://developers.facebook.com/docs/whatsapp)
- [WhatsApp Cloud API Reference](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [Message Templates Guide](https://developers.facebook.com/docs/whatsapp/message-templates)
- [WhatsApp Business Pricing](https://developers.facebook.com/docs/whatsapp/pricing)

## Support

For issues specific to:
- **WhatsApp API**: Check Meta for Developers documentation
- **This Integration**: Create an issue in the project repository
- **Billing**: Contact Meta Business Support

---

**Last Updated**: November 2024
