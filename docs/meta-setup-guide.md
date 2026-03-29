# Meta Developer App Setup — Area6 Social Publisher

## What We're Building

Automated publishing of health tip images and Reels to Instagram and Facebook for Area6 / qualitylife.lk. No app review needed — we're publishing to our own accounts only (Standard Access).

---

## Prerequisites

- [ ] Facebook account (personal — used to create the developer app)
- [ ] Facebook Page for Area6 (create one if it doesn't exist)
- [ ] Instagram Business or Creator account for Area6 (linked to the Facebook Page)

---

## Step 1: Convert Instagram to Business Account

Skip if already a Business/Creator account.

1. Open Instagram app → Settings → Account → Switch to Professional Account
2. Choose **Business**
3. Select category: **Gym / Physical Fitness**
4. Link to your **Area6 Facebook Page**

---

## Step 2: Create a Facebook Page (if needed)

1. Go to https://www.facebook.com/pages/create
2. Page name: **Area6 - Quality Life Fitness** (or whatever the brand is)
3. Category: **Gym / Physical Fitness**
4. Add logo, cover photo, description
5. Make sure the Instagram Business account is linked to this Page

---

## Step 3: Create Meta Developer App

1. Go to https://developers.facebook.com/
2. Click **My Apps** → **Create App**
3. Select **Other** → **Business** (or **None** if no Business Manager)
4. App name: `Area6 Social Publisher`
5. Contact email: your email
6. Click **Create App**

---

## Step 4: Add Instagram Graph API Product

1. In your app dashboard, click **Add Product**
2. Find **Instagram Graph API** → click **Set Up**
3. This enables the Instagram API endpoints

---

## Step 5: Add Facebook Login Product

1. Click **Add Product** again
2. Find **Facebook Login for Business** → click **Set Up**
3. Under Settings:
   - Valid OAuth Redirect URIs: `https://localhost/callback`
   - (We'll use this for the token flow)

---

## Step 6: Get Permissions (Standard Access)

Go to **App Review** → **Permissions and Features**. These should be available at Standard Access (no review needed for your own accounts):

- `instagram_basic` — Read profile info
- `instagram_content_publish` — Publish posts, reels, stories
- `pages_show_list` — List your Pages
- `pages_read_engagement` — Read Page engagement data
- `pages_manage_posts` — Publish to Facebook Page
- `business_management` — (if using Business Manager)

**Note:** Standard Access = works for app admins/developers only. That's us.

---

## Step 7: Generate Access Tokens

### Short-lived token (for testing)

1. Go to https://developers.facebook.com/tools/explorer/
2. Select your app from the dropdown
3. Click **Generate Access Token**
4. Grant all the permissions listed above
5. Copy the token — it expires in ~1 hour

### Long-lived token (for automation)

Exchange the short-lived token for a long-lived one (60 days):

```bash
curl -s "https://graph.facebook.com/v25.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id=YOUR_APP_ID&\
client_secret=YOUR_APP_SECRET&\
fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
```

Save the response — the `access_token` is valid for 60 days.

### Get Instagram Business Account ID

```bash
# Get your Facebook Pages
curl -s "https://graph.facebook.com/v25.0/me/accounts?access_token=YOUR_TOKEN"

# Get Instagram account linked to the Page
curl -s "https://graph.facebook.com/v25.0/PAGE_ID?fields=instagram_business_account&access_token=YOUR_TOKEN"
```

Save the `instagram_business_account.id` — we need this for publishing.

---

## Step 8: Share Credentials with OpenClaw

Once you have these values, share them (DM, not in a public channel):

```
META_APP_ID=...
META_APP_SECRET=...
META_ACCESS_TOKEN=...           # long-lived token
META_PAGE_ID=...                # Facebook Page ID
INSTAGRAM_BUSINESS_ACCOUNT_ID=... # Instagram Business Account ID
```

I'll save them to `/home/chanclaw/.openclaw/credentials/meta-credentials.json` and wire up the publishing pipeline.

---

## Step 9: Token Refresh (automated)

Long-lived tokens expire after 60 days. We'll set up a cron to auto-refresh before expiry:

```bash
curl -s "https://graph.facebook.com/v25.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id=APP_ID&\
client_secret=APP_SECRET&\
fb_exchange_token=CURRENT_LONG_LIVED_TOKEN"
```

Unlike Google's 7-day testing mode tokens, Meta's long-lived tokens can be refreshed indefinitely as long as you refresh before they expire.

---

## API Endpoints We'll Use

### Instagram — Publish a Photo Post
```bash
# Step 1: Create media container
curl -X POST "https://graph.facebook.com/v25.0/IG_USER_ID/media" \
  -d "image_url=PUBLIC_IMAGE_URL" \
  -d "caption=Your caption here #hashtags" \
  -d "access_token=TOKEN"

# Step 2: Publish the container
curl -X POST "https://graph.facebook.com/v25.0/IG_USER_ID/media_publish" \
  -d "creation_id=CONTAINER_ID" \
  -d "access_token=TOKEN"
```

### Instagram — Publish a Reel
```bash
# Step 1: Create video container
curl -X POST "https://graph.facebook.com/v25.0/IG_USER_ID/media" \
  -d "video_url=PUBLIC_VIDEO_URL" \
  -d "caption=Your caption" \
  -d "media_type=REELS" \
  -d "access_token=TOKEN"

# Step 2: Wait for processing, then publish
curl -X POST "https://graph.facebook.com/v25.0/IG_USER_ID/media_publish" \
  -d "creation_id=CONTAINER_ID" \
  -d "access_token=TOKEN"
```

### Facebook Page — Publish a Photo
```bash
curl -X POST "https://graph.facebook.com/v25.0/PAGE_ID/photos" \
  -d "url=PUBLIC_IMAGE_URL" \
  -d "message=Your caption" \
  -d "access_token=PAGE_TOKEN"
```

### Facebook Page — Publish a Video/Reel
```bash
curl -X POST "https://graph.facebook.com/v25.0/PAGE_ID/video_reels" \
  -d "upload_phase=start" \
  -d "access_token=PAGE_TOKEN"
# Then upload video bytes + finish phase
```

**Important:** Instagram requires media to be accessible via a **public URL**. We'll need to either:
- Upload to a temp hosting (e.g., Cloudflare R2, or our server with a public endpoint)
- Or use the resumable upload flow (upload bytes directly)

---

## Architecture Overview

```
Daily Cron (6AM SL)
    │
    ├── Gemini 2.5 Flash → Generate tip text
    ├── Imagen 4 Fast → Generate background image
    ├── Pillow → Overlay text on image (1080x1080 for posts)
    ├── Piper TTS → Generate narration audio
    ├── FFmpeg → Mux into Reel (1080x1920, ≤60s)
    │
    └── Publish:
        ├── YouTube Shorts (already done ✅)
        ├── Instagram → Photo post + Reel
        ├── Facebook Page → Photo post + Reel
        └── (future) TikTok → Video
```

---

## Timeline

1. **You** — Set up Meta Developer App + link Instagram Business account (~30 min)
2. **OpenClaw** — Build the publishing scripts and integrate into pipeline (~2 hours)
3. **Test** — Publish a test post to Instagram + Facebook
4. **Automate** — Add to daily cron alongside YouTube uploads

---

## Notes

- No app review needed for Standard Access (own accounts only)
- Long-lived tokens last 60 days (vs Google's 7-day testing mode)
- Rate limit: 200 API calls/hour — more than enough for our ~2 posts/day
- Instagram requires Business/Creator account (not Personal)
- All media must be publicly accessible URLs for the container API
