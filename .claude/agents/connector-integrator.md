# Connector Integrator Agent

## Purpose
Implement secure, efficient connectors for Google Drive, Gmail, Notion, and local file systems to unify knowledge access across user ecosystems.

## Expertise
- OAuth 2.0 implementation
- Google APIs (Drive, Gmail)
- Notion API integration
- File System Access API
- Incremental sync algorithms
- Conflict resolution
- Rate limiting and backoff
- Data deduplication
- Privacy-preserving indexing

## Context
- **Sprint 65**: Connectors implementation
- **Goal**: Unified search across all user data sources
- **Privacy**: User data never leaves their control
- **Reference**: ROADMAP.md connector specifications

## Connector Architecture

### 1. OAuth Flow Manager
```javascript
class OAuthManager {
  constructor() {
    this.providers = {
      google: {
        authUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
        tokenUrl: 'https://oauth2.googleapis.com/token',
        scopes: [
          'https://www.googleapis.com/auth/drive.readonly',
          'https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/userinfo.email'
        ]
      },
      notion: {
        authUrl: 'https://api.notion.com/v1/oauth/authorize',
        tokenUrl: 'https://api.notion.com/v1/oauth/token',
        scopes: ['read_content', 'read_user']
      }
    };

    this.tokens = new Map(); // In production, store encrypted
  }

  async initiateAuth(provider) {
    const config = this.providers[provider];
    const state = crypto.randomUUID();
    const codeVerifier = this.generateCodeVerifier();
    const codeChallenge = await this.generateCodeChallenge(codeVerifier);

    // Store state and verifier for callback
    sessionStorage.setItem(`oauth_${state}`, JSON.stringify({
      provider,
      codeVerifier,
      timestamp: Date.now()
    }));

    const params = new URLSearchParams({
      client_id: process.env[`${provider.toUpperCase()}_CLIENT_ID`],
      redirect_uri: `${window.location.origin}/auth/callback`,
      response_type: 'code',
      scope: config.scopes.join(' '),
      state,
      code_challenge: codeChallenge,
      code_challenge_method: 'S256',
      access_type: 'offline', // For refresh tokens
      prompt: 'consent'
    });

    window.location.href = `${config.authUrl}?${params}`;
  }

  async handleCallback(code, state) {
    const stored = sessionStorage.getItem(`oauth_${state}`);
    if (!stored) throw new Error('Invalid OAuth state');

    const { provider, codeVerifier } = JSON.parse(stored);
    const config = this.providers[provider];

    // Exchange code for tokens
    const response = await fetch(config.tokenUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: process.env[`${provider.toUpperCase()}_CLIENT_ID`],
        client_secret: process.env[`${provider.toUpperCase()}_CLIENT_SECRET`],
        code,
        code_verifier: codeVerifier,
        grant_type: 'authorization_code',
        redirect_uri: `${window.location.origin}/auth/callback`
      })
    });

    const tokens = await response.json();
    await this.storeTokens(provider, tokens);

    // Clean up
    sessionStorage.removeItem(`oauth_${state}`);

    return tokens;
  }

  async refreshToken(provider) {
    const stored = await this.getStoredTokens(provider);
    if (!stored?.refresh_token) throw new Error('No refresh token');

    const config = this.providers[provider];
    const response = await fetch(config.tokenUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: process.env[`${provider.toUpperCase()}_CLIENT_ID`],
        client_secret: process.env[`${provider.toUpperCase()}_CLIENT_SECRET`],
        refresh_token: stored.refresh_token,
        grant_type: 'refresh_token'
      })
    });

    const tokens = await response.json();
    await this.storeTokens(provider, { ...stored, ...tokens });
    return tokens;
  }
}
```

### 2. Google Drive Connector
```javascript
class GoogleDriveConnector {
  constructor(oauthManager) {
    this.oauth = oauthManager;
    this.baseUrl = 'https://www.googleapis.com/drive/v3';
    this.syncState = new Map(); // Track sync state per folder
  }

  async listFiles(query = {}) {
    const token = await this.oauth.getAccessToken('google');

    const params = new URLSearchParams({
      pageSize: query.limit || 100,
      fields: 'files(id,name,mimeType,modifiedTime,size,parents,webViewLink)',
      orderBy: 'modifiedTime desc',
      q: query.q || "trashed = false",
      pageToken: query.pageToken || ''
    });

    const response = await fetch(`${this.baseUrl}/files?${params}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    return response.json();
  }

  async getFileContent(fileId) {
    const token = await this.oauth.getAccessToken('google');

    // First get file metadata
    const metaResponse = await fetch(`${this.baseUrl}/files/${fileId}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const metadata = await metaResponse.json();

    // Handle different file types
    if (metadata.mimeType.startsWith('application/vnd.google-apps')) {
      // Google Docs/Sheets/Slides - export as text
      return this.exportGoogleDoc(fileId, metadata.mimeType);
    } else if (metadata.mimeType.startsWith('text/')) {
      // Text files - download directly
      const response = await fetch(`${this.baseUrl}/files/${fileId}?alt=media`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      return response.text();
    } else {
      // Binary files - return metadata only
      return {
        id: fileId,
        name: metadata.name,
        mimeType: metadata.mimeType,
        size: metadata.size,
        cannotIndex: true
      };
    }
  }

  async exportGoogleDoc(fileId, mimeType) {
    const token = await this.oauth.getAccessToken('google');

    // Map Google types to export formats
    const exportMap = {
      'application/vnd.google-apps.document': 'text/plain',
      'application/vnd.google-apps.spreadsheet': 'text/csv',
      'application/vnd.google-apps.presentation': 'text/plain'
    };

    const exportType = exportMap[mimeType] || 'text/plain';

    const response = await fetch(
      `${this.baseUrl}/files/${fileId}/export?mimeType=${exportType}`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    return response.text();
  }

  async syncFolder(folderId, since = null) {
    const changes = [];
    let pageToken = null;

    // Build query for changed files
    let query = `'${folderId}' in parents and trashed = false`;
    if (since) {
      query += ` and modifiedTime > '${since.toISOString()}'`;
    }

    do {
      const result = await this.listFiles({ q: query, pageToken });
      changes.push(...result.files);
      pageToken = result.nextPageToken;
    } while (pageToken);

    // Update sync state
    this.syncState.set(folderId, {
      lastSync: new Date().toISOString(),
      fileCount: changes.length
    });

    return changes;
  }
}
```

### 3. Gmail Connector
```javascript
class GmailConnector {
  constructor(oauthManager) {
    this.oauth = oauthManager;
    this.baseUrl = 'https://gmail.googleapis.com/gmail/v1';
  }

  async searchMessages(query) {
    const token = await this.oauth.getAccessToken('google');

    const params = new URLSearchParams({
      q: query,
      maxResults: 50
    });

    const response = await fetch(
      `${this.baseUrl}/users/me/messages?${params}`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    const result = await response.json();

    // Fetch full message details
    const messages = await Promise.all(
      (result.messages || []).map(m => this.getMessage(m.id))
    );

    return messages;
  }

  async getMessage(messageId) {
    const token = await this.oauth.getAccessToken('google');

    const response = await fetch(
      `${this.baseUrl}/users/me/messages/${messageId}`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    const message = await response.json();

    // Parse message parts
    const parsed = this.parseMessage(message);

    return {
      id: message.id,
      threadId: message.threadId,
      subject: parsed.headers.subject,
      from: parsed.headers.from,
      to: parsed.headers.to,
      date: parsed.headers.date,
      snippet: message.snippet,
      body: parsed.body,
      attachments: parsed.attachments
    };
  }

  parseMessage(message) {
    const headers = {};
    const attachments = [];
    let body = '';

    // Extract headers
    message.payload.headers.forEach(h => {
      headers[h.name.toLowerCase()] = h.value;
    });

    // Extract body and attachments recursively
    const extractParts = (part) => {
      if (part.mimeType === 'text/plain' && part.body.data) {
        body += Buffer.from(part.body.data, 'base64').toString();
      } else if (part.filename) {
        attachments.push({
          filename: part.filename,
          mimeType: part.mimeType,
          size: part.body.size
        });
      }

      if (part.parts) {
        part.parts.forEach(extractParts);
      }
    };

    extractParts(message.payload);

    return { headers, body, attachments };
  }
}
```

### 4. Notion Connector
```javascript
class NotionConnector {
  constructor(oauthManager) {
    this.oauth = oauthManager;
    this.baseUrl = 'https://api.notion.com/v1';
  }

  async searchContent(query) {
    const token = await this.oauth.getAccessToken('notion');

    const response = await fetch(`${this.baseUrl}/search`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        query,
        filter: { property: 'object', value: 'page' },
        page_size: 100
      })
    });

    return response.json();
  }

  async getPage(pageId) {
    const token = await this.oauth.getAccessToken('notion');

    // Get page metadata
    const pageResponse = await fetch(`${this.baseUrl}/pages/${pageId}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Notion-Version': '2022-06-28'
      }
    });
    const page = await pageResponse.json();

    // Get page content blocks
    const blocksResponse = await fetch(
      `${this.baseUrl}/blocks/${pageId}/children?page_size=100`,
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Notion-Version': '2022-06-28'
        }
      }
    );
    const blocks = await blocksResponse.json();

    // Convert blocks to plain text
    const content = this.blocksToText(blocks.results);

    return {
      id: pageId,
      title: this.extractTitle(page),
      content,
      lastEdited: page.last_edited_time,
      url: page.url
    };
  }

  blocksToText(blocks) {
    let text = '';

    for (const block of blocks) {
      switch (block.type) {
        case 'paragraph':
        case 'heading_1':
        case 'heading_2':
        case 'heading_3':
        case 'quote':
        case 'callout':
          text += this.richTextToPlain(block[block.type].rich_text) + '\n\n';
          break;
        case 'bulleted_list_item':
        case 'numbered_list_item':
          text += '• ' + this.richTextToPlain(block[block.type].rich_text) + '\n';
          break;
        case 'code':
          text += '```' + block.code.language + '\n';
          text += this.richTextToPlain(block.code.rich_text) + '\n```\n\n';
          break;
        case 'image':
          text += `[Image: ${block.image.caption}]\n\n`;
          break;
      }
    }

    return text.trim();
  }

  richTextToPlain(richTextArray) {
    return richTextArray.map(rt => rt.plain_text).join('');
  }
}
```

### 5. Local File System Connector
```javascript
class LocalFileConnector {
  constructor() {
    this.fileSystemAccess = 'showDirectoryPicker' in window;
    this.watchedDirectories = new Map();
  }

  async selectDirectory() {
    if (!this.fileSystemAccess) {
      throw new Error('File System Access API not supported');
    }

    try {
      const dirHandle = await window.showDirectoryPicker({
        mode: 'read'
      });

      // Request persistent permission
      const permission = await dirHandle.requestPermission({ mode: 'read' });
      if (permission !== 'granted') {
        throw new Error('Permission denied');
      }

      // Store handle for future access
      await this.storeDirectoryHandle(dirHandle);

      return dirHandle;
    } catch (error) {
      console.error('Directory selection failed:', error);
      throw error;
    }
  }

  async scanDirectory(dirHandle, options = {}) {
    const files = [];
    const {
      extensions = ['.md', '.txt', '.pdf', '.docx'],
      maxDepth = 5,
      maxFiles = 1000
    } = options;

    async function* traverse(handle, path = '', depth = 0) {
      if (depth > maxDepth) return;

      for await (const entry of handle.values()) {
        const entryPath = path ? `${path}/${entry.name}` : entry.name;

        if (entry.kind === 'file') {
          // Check extension
          const ext = entry.name.substring(entry.name.lastIndexOf('.'));
          if (extensions.includes(ext.toLowerCase())) {
            yield { handle: entry, path: entryPath };
          }
        } else if (entry.kind === 'directory') {
          // Recursively scan subdirectories
          yield* traverse(entry, entryPath, depth + 1);
        }
      }
    }

    for await (const file of traverse(dirHandle)) {
      files.push(file);
      if (files.length >= maxFiles) break;
    }

    return files;
  }

  async readFile(fileHandle) {
    try {
      const file = await fileHandle.getFile();

      if (file.size > 10 * 1024 * 1024) { // 10MB limit
        return {
          name: file.name,
          size: file.size,
          error: 'File too large to index'
        };
      }

      const content = await file.text();
      return {
        name: file.name,
        content,
        size: file.size,
        lastModified: new Date(file.lastModified).toISOString()
      };
    } catch (error) {
      return {
        name: fileHandle.name,
        error: error.message
      };
    }
  }

  async watchDirectory(dirHandle) {
    // Note: File System Observer API is still experimental
    // Fallback to periodic scanning for now
    const watchId = crypto.randomUUID();

    this.watchedDirectories.set(watchId, {
      handle: dirHandle,
      lastScan: new Date(),
      interval: setInterval(async () => {
        await this.checkForChanges(watchId);
      }, 60000) // Check every minute
    });

    return watchId;
  }

  async checkForChanges(watchId) {
    const watch = this.watchedDirectories.get(watchId);
    if (!watch) return;

    const files = await this.scanDirectory(watch.handle);
    // Compare with previous scan and emit changes
    // Implementation depends on storage strategy
  }
}
```

## Unified Search

```javascript
class UnifiedSearch {
  constructor(connectors) {
    this.connectors = connectors;
  }

  async search(query, options = {}) {
    const {
      sources = ['drive', 'gmail', 'notion', 'local'],
      limit = 50
    } = options;

    // Search all sources in parallel
    const searches = sources.map(source =>
      this.searchSource(source, query, limit)
        .catch(err => ({ source, error: err.message }))
    );

    const results = await Promise.allSettled(searches);

    // Merge and rank results
    const merged = this.mergeResults(results);
    return this.rankResults(merged, query);
  }

  async searchSource(source, query, limit) {
    switch (source) {
      case 'drive':
        return this.connectors.drive.searchFiles(query);
      case 'gmail':
        return this.connectors.gmail.searchMessages(query);
      case 'notion':
        return this.connectors.notion.searchContent(query);
      case 'local':
        return this.connectors.local.searchLocal(query);
      default:
        throw new Error(`Unknown source: ${source}`);
    }
  }

  mergeResults(results) {
    const merged = [];

    for (const result of results) {
      if (result.status === 'fulfilled') {
        merged.push(...result.value);
      }
    }

    return merged;
  }

  rankResults(results, query) {
    // Score based on relevance
    const scored = results.map(result => ({
      ...result,
      score: this.calculateRelevance(result, query)
    }));

    return scored
      .sort((a, b) => b.score - a.score)
      .slice(0, 50);
  }
}
```

## Privacy & Security

- All OAuth tokens encrypted at rest
- Refresh tokens stored separately with additional encryption
- Content never leaves user's control (no server-side indexing)
- Local indexing with user consent
- Automatic token expiry and refresh
- Audit log of all connector access

## References
- [Google Drive API](https://developers.google.com/drive/api/v3)
- [Gmail API](https://developers.google.com/gmail/api)
- [Notion API](https://developers.notion.com/)
- [File System Access API](https://web.dev/file-system-access/)
- ROADMAP.md Sprint 65 requirements
