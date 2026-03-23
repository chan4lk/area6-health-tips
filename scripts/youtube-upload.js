#!/usr/bin/env node
/**
 * Upload Area6 health tip Shorts to YouTube.
 *
 * Usage:
 *   node scripts/youtube-upload.js output/sleep.mp4
 *   node scripts/youtube-upload.js output/sleep.mp4 --public
 *   node scripts/youtube-upload.js --all                  # upload all output/*.mp4
 *   node scripts/youtube-upload.js --all --public
 *
 * Reads the matching JSON from content/tips/<id>.json to populate title,
 * description, tags, and category. Uploads as Shorts (vertical ≤60s).
 *
 * Tracks uploaded videos in scripts/upload-log.json to avoid duplicates.
 */
const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const ROOT = path.resolve(__dirname, '..');
const TIPS_DIR = path.join(ROOT, 'content', 'tips');
const OUTPUT_DIR = path.join(ROOT, 'output');
const UPLOAD_LOG = path.join(__dirname, 'upload-log.json');

const CREDS_PATH = '/home/chanclaw/.openclaw/credentials/google-client.json';
const TOKEN_PATH = '/home/chanclaw/.openclaw/credentials/google-token.json';

const CHANNEL_ID = 'UCRocfsBHK3AlK3TlUUX-HiQ';
const PLAYLIST_NAME = 'Health Tips - Sinhala';

// Category IDs: 22 = People & Blogs, 26 = How-to & Style, 27 = Education
const CATEGORY_MAP = {
  sleep: '27', exercise: '17', nutrition: '26', hydration: '27',
  mental: '27', posture: '26', habits: '27', recovery: '17',
  breathing: '26', 'gut-health': '27',
};

function loadUploadLog() {
  try { return JSON.parse(fs.readFileSync(UPLOAD_LOG, 'utf8')); }
  catch { return {}; }
}

function saveUploadLog(log) {
  fs.writeFileSync(UPLOAD_LOG, JSON.stringify(log, null, 2));
}

function loadTip(videoPath) {
  const id = path.basename(videoPath, '.mp4');
  const jsonPath = path.join(TIPS_DIR, `${id}.json`);
  if (!fs.existsSync(jsonPath)) return null;
  return JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
}

function buildMetadata(tip, isPublic) {
  const hashtags = (tip.hashtags || []).join(' ');
  const description = [
    tip.tip,
    '',
    `Category: ${tip.category}`,
    '',
    hashtags,
    '',
    '🌐 qualitylife.lk | Area6 Fitness',
    '#Shorts',
  ].join('\n');

  return {
    title: `${tip.title} | qualitylife.lk #Shorts`,
    description,
    tags: [
      ...(tip.hashtags || []).map(h => h.replace('#', '')),
      'Shorts', 'health tips', 'sinhala', 'qualitylife', 'area6',
      tip.category,
    ],
    categoryId: CATEGORY_MAP[tip.category] || '27',
    privacy: isPublic ? 'public' : 'private',
  };
}

async function getAuth() {
  const creds = JSON.parse(fs.readFileSync(CREDS_PATH));
  const { client_id, client_secret } = creds.installed;
  const oauth2 = new google.auth.OAuth2(client_id, client_secret, 'http://localhost');
  const tokens = JSON.parse(fs.readFileSync(TOKEN_PATH));
  oauth2.setCredentials(tokens);
  oauth2.on('tokens', (t) => {
    const merged = { ...tokens, ...t };
    fs.writeFileSync(TOKEN_PATH, JSON.stringify(merged, null, 2));
  });
  return oauth2;
}

async function findOrCreatePlaylist(youtube) {
  let pageToken = '';
  do {
    const res = await youtube.playlists.list({
      part: 'snippet', mine: true, maxResults: 50,
      pageToken: pageToken || undefined,
    });
    for (const item of (res.data.items || [])) {
      if (item.snippet.title === PLAYLIST_NAME) return item.id;
    }
    pageToken = res.data.nextPageToken;
  } while (pageToken);

  const res = await youtube.playlists.insert({
    part: 'snippet,status',
    requestBody: {
      snippet: { title: PLAYLIST_NAME, description: 'Sinhala health tips by qualitylife.lk / Area6 Fitness' },
      status: { privacyStatus: 'public' },
    },
  });
  console.log(`📋 Created playlist: ${PLAYLIST_NAME} (${res.data.id})`);
  return res.data.id;
}

async function uploadOne(youtube, videoPath, isPublic) {
  const tip = loadTip(videoPath);
  if (!tip) {
    console.error(`⚠️  No tip JSON for ${path.basename(videoPath)}, skipping`);
    return null;
  }

  const meta = buildMetadata(tip, isPublic);
  const fileSize = fs.statSync(videoPath).size;
  console.log(`\n⬆️  Uploading: ${path.basename(videoPath)} (${(fileSize / 1024 / 1024).toFixed(1)} MB)`);
  console.log(`   Title: ${meta.title}`);
  console.log(`   Privacy: ${meta.privacy}`);

  const res = await youtube.videos.insert({
    part: 'snippet,status',
    requestBody: {
      snippet: {
        title: meta.title,
        description: meta.description,
        tags: meta.tags,
        categoryId: meta.categoryId,
      },
      status: {
        privacyStatus: meta.privacy,
        selfDeclaredMadeForKids: false,
        shorts: { shortsVideoVisibility: 'SHORTS_VIDEO_VISIBILITY_VISIBLE' },
      },
    },
    media: { body: fs.createReadStream(videoPath) },
  }, {
    onUploadProgress: (evt) => {
      process.stdout.write(`\r   Progress: ${(evt.bytesRead / fileSize * 100).toFixed(0)}%`);
    },
  });

  const videoId = res.data.id;
  const url = `https://youtube.com/shorts/${videoId}`;
  console.log(`\n   ✅ ${url}`);
  return { videoId, url, tip };
}

async function main() {
  const args = process.argv.slice(2);
  const isPublic = args.includes('--public');
  const isAll = args.includes('--all');
  const dryRun = args.includes('--dry-run');

  let files = [];
  if (isAll) {
    files = fs.readdirSync(OUTPUT_DIR)
      .filter(f => f.endsWith('.mp4') && f !== 'slide_001.mp4')
      .map(f => path.join(OUTPUT_DIR, f));
  } else {
    const explicit = args.filter(a => !a.startsWith('--'));
    if (!explicit.length) {
      console.error('Usage: node scripts/youtube-upload.js <video.mp4|--all> [--public] [--dry-run]');
      process.exit(1);
    }
    files = explicit.map(f => path.resolve(f));
  }

  const log = loadUploadLog();
  const toUpload = files.filter(f => {
    const id = path.basename(f, '.mp4');
    if (log[id]) { console.log(`⏭️  Already uploaded: ${id} → ${log[id].url}`); return false; }
    return true;
  });

  if (!toUpload.length) { console.log('\n✅ Nothing new to upload.'); return; }
  console.log(`\n📦 ${toUpload.length} video(s) to upload${isPublic ? ' (PUBLIC)' : ' (PRIVATE)'}${dryRun ? ' [DRY RUN]' : ''}`);

  if (dryRun) {
    toUpload.forEach(f => {
      const tip = loadTip(f);
      if (tip) console.log(`  - ${tip.id}: ${tip.title}`);
    });
    return;
  }

  const auth = await getAuth();
  const youtube = google.youtube({ version: 'v3', auth });

  const results = [];
  for (const file of toUpload) {
    try {
      const result = await uploadOne(youtube, file, isPublic);
      if (result) {
        log[result.tip.id] = { videoId: result.videoId, url: result.url, uploadedAt: new Date().toISOString() };
        saveUploadLog(log);
        results.push(result);
      }
    } catch (e) {
      console.error(`\n❌ Failed ${path.basename(file)}: ${e.message}`);
      if (e.message.includes('quotaExceeded') || e.message.includes('exceeded the number of videos')) {
        console.error('YouTube upload limit reached. Try again tomorrow.');
        break;
      }
    }

    // Small delay between uploads
    if (toUpload.indexOf(file) < toUpload.length - 1) {
      await new Promise(r => setTimeout(r, 2000));
    }
  }

  console.log(`\n🎉 Done! ${results.length}/${toUpload.length} uploaded.`);
}

main().catch(e => {
  console.error(`\n❌ ${e.message}`);
  process.exit(1);
});
