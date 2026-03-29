#!/usr/bin/env node
/**
 * Upload Area6 health tip Shorts to YouTube.
 *
 * Usage:
 *   node scripts/youtube-upload.js --batch 2026-03-23-en           # upload a batch
 *   node scripts/youtube-upload.js --batch 2026-03-23-en --public  # as public
 *   node scripts/youtube-upload.js --batch 2026-03-23-en --dry-run # preview
 *   node scripts/youtube-upload.js --latest                        # latest batch
 *   node scripts/youtube-upload.js output/2026-03-23-en/sleep.mp4  # single file
 *
 * Tracks uploads in published/<batch>/manifest.json.
 * Moves uploaded MP4s to published/<batch>/ after upload.
 */
const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const ROOT = path.resolve(__dirname, '..');
const TIPS_DIR = path.join(ROOT, 'content', 'tips');
const OUTPUT_DIR = path.join(ROOT, 'output');
const PUBLISHED_DIR = path.join(ROOT, 'published');

const CREDS_PATH = '/home/chanclaw/.openclaw/credentials/google-client.json';
const TOKEN_PATH = '/home/chanclaw/.openclaw/credentials/google-token.json';

const CHANNEL_ID = 'UCRocfsBHK3AlK3TlUUX-HiQ';

const CATEGORY_MAP = {
  sleep: '27', exercise: '17', nutrition: '26', hydration: '27',
  mental: '27', posture: '26', habits: '27', recovery: '17',
  breathing: '26', 'gut-health': '27',
};

function loadManifest(batch) {
  const p = path.join(PUBLISHED_DIR, batch, 'manifest.json');
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); }
  catch { return { batch, uploads: {} }; }
}

function saveManifest(batch, manifest) {
  const dir = path.join(PUBLISHED_DIR, batch);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(manifest, null, 2));
}

function findTip(videoPath, batch) {
  const id = path.basename(videoPath, '.mp4');
  // Try batch folder first, then flat
  const candidates = [
    path.join(TIPS_DIR, batch, `${id}.json`),
    path.join(TIPS_DIR, `${id}.json`),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, 'utf8'));
  }
  return null;
}

function detectLanguage(text) {
  const sinhala = [...text].filter(c => c.charCodeAt(0) >= 0x0D80 && c.charCodeAt(0) <= 0x0DFF).length;
  return sinhala > text.length * 0.3 ? 'si' : 'en';
}

function buildMetadata(tip, isPublic) {
  const lang = detectLanguage(tip.tip);
  const hashtags = (tip.hashtags || []).join(' ');
  const description = [
    tip.tip, '',
    `Category: ${tip.category}`, '',
    hashtags, '',
    '🌐 qualitylife.lk | Area6 Fitness',
    '#Shorts',
  ].join('\n');

  const langTags = lang === 'si'
    ? ['sinhala', 'sri lanka', 'සෞඛ්‍යය']
    : ['health tips', 'fitness', 'wellness'];

  return {
    title: `${tip.title} | qualitylife.lk #Shorts`,
    description,
    tags: [
      ...(tip.hashtags || []).map(h => h.replace('#', '')),
      'Shorts', 'qualitylife', 'area6', tip.category,
      ...langTags,
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

async function uploadOne(youtube, videoPath, tip, isPublic) {
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
  return { videoId, url };
}

function listBatches() {
  if (!fs.existsSync(OUTPUT_DIR)) return [];
  return fs.readdirSync(OUTPUT_DIR)
    .filter(d => fs.statSync(path.join(OUTPUT_DIR, d)).isDirectory())
    .sort();
}

async function uploadBatch(youtube, batch, isPublic, dryRun) {
  const batchDir = path.join(OUTPUT_DIR, batch);
  if (!fs.existsSync(batchDir)) return { uploaded: 0, total: 0, rateLimited: false };

  const files = fs.readdirSync(batchDir)
    .filter(f => f.endsWith('.mp4'))
    .map(f => path.join(batchDir, f));

  const manifest = loadManifest(batch);
  const toUpload = [];
  for (const f of files) {
    const id = path.basename(f, '.mp4');
    if (manifest.uploads[id]) continue;
    const tip = findTip(f, batch);
    if (!tip) { console.error(`⚠️  No tip JSON for ${id}, skipping`); continue; }
    toUpload.push({ file: f, id, tip });
  }

  if (!toUpload.length) return { uploaded: 0, total: 0, rateLimited: false };

  console.log(`\n📦 Batch "${batch}": ${toUpload.length} video(s)${isPublic ? ' (PUBLIC)' : ' (PRIVATE)'}${dryRun ? ' [DRY RUN]' : ''}`);

  if (dryRun) {
    toUpload.forEach(({ tip }) => console.log(`  - ${tip.id}: ${tip.title}`));
    return { uploaded: 0, total: toUpload.length, rateLimited: false };
  }

  const pubDir = path.join(PUBLISHED_DIR, batch);
  fs.mkdirSync(pubDir, { recursive: true });

  let uploaded = 0;
  let rateLimited = false;
  for (const { file, id, tip } of toUpload) {
    try {
      const result = await uploadOne(youtube, file, tip, isPublic);
      manifest.uploads[id] = {
        videoId: result.videoId,
        url: result.url,
        title: tip.title,
        category: tip.category,
        uploadedAt: new Date().toISOString(),
        privacy: isPublic ? 'public' : 'private',
      };
      saveManifest(batch, manifest);

      // Move MP4 to published/
      const dest = path.join(pubDir, path.basename(file));
      fs.copyFileSync(file, dest);
      fs.unlinkSync(file);
      uploaded++;
    } catch (e) {
      console.error(`\n❌ Failed ${path.basename(file)}: ${e.message}`);
      if (e.message.includes('quotaExceeded') || e.message.includes('exceeded the number of videos')) {
        console.error('YouTube upload limit reached. Try again tomorrow.');
        rateLimited = true;
        break;
      }
    }

    await new Promise(r => setTimeout(r, 2000));
  }

  return { uploaded, total: toUpload.length, rateLimited };
}

async function main() {
  const args = process.argv.slice(2);
  const isPublic = args.includes('--public');
  const dryRun = args.includes('--dry-run');
  const isLatest = args.includes('--latest');
  const isAll = args.includes('--all');
  const batchIdx = args.indexOf('--batch');

  let batches = [];

  if (batchIdx >= 0 && args[batchIdx + 1]) {
    batches = [args[batchIdx + 1]];
  } else if (isAll) {
    batches = listBatches();
  } else if (isLatest) {
    const all = listBatches();
    if (!all.length) { console.log('No batches found.'); return; }
    batches = [all[all.length - 1]];
  } else {
    const explicit = args.filter(a => !a.startsWith('--'));
    if (!explicit.length) {
      console.error('Usage: node scripts/youtube-upload.js --all|--latest|--batch <name>|<file.mp4> [--public] [--dry-run]');
      console.error(`\nAvailable batches: ${listBatches().join(', ')}`);
      process.exit(1);
    }
    // Single file upload — infer batch
    const files = explicit.map(f => path.resolve(f));
    const batch = path.basename(path.dirname(files[0]));
    batches = [batch === 'output' ? 'misc' : batch];
  }

  if (!batches.length) { console.log('No batches found in output/.'); return; }

  let auth, youtube;
  if (!dryRun) {
    auth = await getAuth();
    youtube = google.youtube({ version: 'v3', auth });
  }

  let totalUploaded = 0;
  for (const batch of batches) {
    const result = await uploadBatch(youtube, batch, isPublic, dryRun);
    totalUploaded += result.uploaded;
    if (result.rateLimited) {
      console.log('\n⛔ Rate limited — stopping. Will continue tomorrow.');
      break;
    }
  }

  console.log(`\n🎉 Total uploaded: ${totalUploaded}`);
}

main().catch(e => {
  console.error(`\n❌ ${e.message}`);
  process.exit(1);
});
