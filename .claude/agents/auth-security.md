# Auth Security Agent

## Purpose
Implement secure authentication, API key management, and BYO (Bring Your Own) key encryption for Sprint 61b using Supabase.

## Expertise
- Supabase authentication (magic links, OAuth)
- API key encryption at rest
- JWT token management
- Anonymous session handling
- Session upgrade flows
- RBAC implementation
- Secure storage patterns
- CSRF/XSS prevention

## Context
- **Sprint 61b**: Add authentication to Magic Box
- **Provider**: Supabase (decided in ROADMAP.md)
- **Requirements**: Magic links, BYO key encryption, anonymous → authenticated upgrade
- **Reference**: ROADMAP.md auth architecture decisions

## Supabase Implementation

### 1. Anonymous Session Management
```javascript
class AnonymousSession {
  constructor() {
    this.sessionId = this.getOrCreateSessionId();
    this.limits = {
      messagesPerHour: 20,
      totalMessages: 100,
      storageMB: 5,
      sessionDays: 7
    };
    this.usage = this.loadUsage();
  }

  getOrCreateSessionId() {
    const stored = localStorage.getItem('relay_anon_id');
    if (stored) {
      const { id, created } = JSON.parse(stored);
      const age = Date.now() - created;

      // Expire after 7 days
      if (age < 7 * 24 * 60 * 60 * 1000) {
        return id;
      }
    }

    // Create new session
    const id = `anon_${crypto.randomUUID()}`;
    localStorage.setItem('relay_anon_id', JSON.stringify({
      id,
      created: Date.now()
    }));

    return id;
  }

  loadUsage() {
    const stored = localStorage.getItem('relay_anon_usage');
    if (stored) {
      return JSON.parse(stored);
    }

    return {
      messagesThisHour: [],
      totalMessages: 0,
      storageBytes: 0
    };
  }

  canSendMessage() {
    // Check hourly limit
    const now = Date.now();
    const oneHourAgo = now - 3600000;
    this.usage.messagesThisHour = this.usage.messagesThisHour.filter(
      timestamp => timestamp > oneHourAgo
    );

    if (this.usage.messagesThisHour.length >= this.limits.messagesPerHour) {
      return {
        allowed: false,
        reason: 'hourly_limit',
        resetIn: Math.min(...this.usage.messagesThisHour) + 3600000 - now
      };
    }

    // Check total limit
    if (this.usage.totalMessages >= this.limits.totalMessages) {
      return {
        allowed: false,
        reason: 'total_limit',
        upgrade: true
      };
    }

    return { allowed: true };
  }

  recordMessage() {
    this.usage.messagesThisHour.push(Date.now());
    this.usage.totalMessages++;
    this.saveUsage();
  }

  saveUsage() {
    localStorage.setItem('relay_anon_usage', JSON.stringify(this.usage));
  }

  upgradeRequired() {
    return this.usage.totalMessages >= this.limits.totalMessages * 0.8;
  }
}
```

### 2. Supabase Auth Setup
```javascript
import { createClient } from '@supabase/supabase-js';

class RelayAuth {
  constructor() {
    this.supabase = createClient(
      process.env.SUPABASE_URL,
      process.env.SUPABASE_ANON_KEY
    );

    this.anonymousSession = new AnonymousSession();
    this.user = null;
    this.session = null;

    this.initializeAuth();
  }

  async initializeAuth() {
    // Check for existing session
    const { data: { session } } = await this.supabase.auth.getSession();

    if (session) {
      this.session = session;
      this.user = session.user;
      await this.migrateAnonymousData();
    }

    // Listen for auth changes
    this.supabase.auth.onAuthStateChange((event, session) => {
      this.handleAuthChange(event, session);
    });
  }

  async handleAuthChange(event, session) {
    console.log('[Auth]', event, session?.user?.email);

    if (event === 'SIGNED_IN') {
      this.session = session;
      this.user = session.user;
      await this.migrateAnonymousData();
      this.onSignIn?.(session);
    } else if (event === 'SIGNED_OUT') {
      this.session = null;
      this.user = null;
      this.anonymousSession = new AnonymousSession();
      this.onSignOut?.();
    }
  }

  async signInWithMagicLink(email) {
    const { error } = await this.supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/magic`
      }
    });

    if (error) {
      throw new Error(`Magic link failed: ${error.message}`);
    }

    return { success: true, message: 'Check your email for the magic link!' };
  }

  async signInWithGoogle() {
    const { error } = await this.supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/magic`
      }
    });

    if (error) {
      throw new Error(`Google sign-in failed: ${error.message}`);
    }
  }

  async signOut() {
    const { error } = await this.supabase.auth.signOut();
    if (error) {
      throw new Error(`Sign-out failed: ${error.message}`);
    }
  }

  isAuthenticated() {
    return this.session !== null;
  }

  async migrateAnonymousData() {
    // Move anonymous session data to user account
    const anonData = localStorage.getItem('relay_anon_history');
    if (anonData && this.user) {
      const history = JSON.parse(anonData);

      // Save to user's account
      const { error } = await this.supabase
        .from('user_data')
        .upsert({
          user_id: this.user.id,
          migrated_history: history,
          migrated_at: new Date().toISOString()
        });

      if (!error) {
        localStorage.removeItem('relay_anon_history');
        console.log('[Auth] Anonymous data migrated');
      }
    }
  }
}
```

### 3. BYO Key Encryption
```javascript
class SecureKeyStorage {
  constructor(supabase) {
    this.supabase = supabase;
    this.encryptionKey = null;
  }

  async initializeEncryption(userId) {
    // Derive user-specific encryption key
    const userSecret = await this.getUserSecret(userId);
    const salt = await this.getOrCreateSalt(userId);

    this.encryptionKey = await this.deriveKey(userSecret, salt);
  }

  async deriveKey(secret, salt) {
    const encoder = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
      'raw',
      encoder.encode(secret),
      'PBKDF2',
      false,
      ['deriveKey']
    );

    return crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: encoder.encode(salt),
        iterations: 100000,
        hash: 'SHA-256'
      },
      keyMaterial,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt']
    );
  }

  async encryptApiKey(apiKey) {
    if (!this.encryptionKey) {
      throw new Error('Encryption not initialized');
    }

    const encoder = new TextEncoder();
    const data = encoder.encode(apiKey);
    const iv = crypto.getRandomValues(new Uint8Array(12));

    const encrypted = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv },
      this.encryptionKey,
      data
    );

    // Combine IV and encrypted data
    const combined = new Uint8Array(iv.length + encrypted.byteLength);
    combined.set(iv, 0);
    combined.set(new Uint8Array(encrypted), iv.length);

    // Convert to base64 for storage
    return btoa(String.fromCharCode(...combined));
  }

  async decryptApiKey(encryptedKey) {
    if (!this.encryptionKey) {
      throw new Error('Encryption not initialized');
    }

    // Decode from base64
    const combined = Uint8Array.from(atob(encryptedKey), c => c.charCodeAt(0));

    // Extract IV and encrypted data
    const iv = combined.slice(0, 12);
    const encrypted = combined.slice(12);

    const decrypted = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv },
      this.encryptionKey,
      encrypted
    );

    const decoder = new TextDecoder();
    return decoder.decode(decrypted);
  }

  async storeApiKey(provider, apiKey) {
    const encrypted = await this.encryptApiKey(apiKey);

    const { error } = await this.supabase
      .from('api_keys')
      .upsert({
        user_id: this.supabase.auth.user().id,
        provider,
        encrypted_key: encrypted,
        updated_at: new Date().toISOString()
      });

    if (error) {
      throw new Error(`Failed to store API key: ${error.message}`);
    }
  }

  async getApiKey(provider) {
    const { data, error } = await this.supabase
      .from('api_keys')
      .select('encrypted_key')
      .eq('user_id', this.supabase.auth.user().id)
      .eq('provider', provider)
      .single();

    if (error || !data) {
      return null;
    }

    return this.decryptApiKey(data.encrypted_key);
  }

  async deleteApiKey(provider) {
    const { error } = await this.supabase
      .from('api_keys')
      .delete()
      .eq('user_id', this.supabase.auth.user().id)
      .eq('provider', provider);

    if (error) {
      throw new Error(`Failed to delete API key: ${error.message}`);
    }
  }
}
```

### 4. Authentication UI Components
```javascript
class AuthUI {
  constructor(container) {
    this.container = container;
    this.auth = new RelayAuth();
    this.render();
  }

  render() {
    if (this.auth.isAuthenticated()) {
      this.renderAuthenticated();
    } else {
      this.renderAnonymous();
    }
  }

  renderAnonymous() {
    const usage = this.auth.anonymousSession.usage;
    const upgradePrompt = this.auth.anonymousSession.upgradeRequired();

    this.container.innerHTML = `
      <div class="auth-status">
        <span class="status-badge anonymous">Anonymous</span>
        <span class="usage">${usage.totalMessages}/100 messages</span>
        ${upgradePrompt ? '<button onclick="authUI.showSignIn()">Upgrade</button>' : ''}
      </div>
    `;
  }

  renderAuthenticated() {
    const user = this.auth.user;

    this.container.innerHTML = `
      <div class="auth-status">
        <span class="status-badge authenticated">Signed in</span>
        <span class="user-email">${user.email}</span>
        <button onclick="authUI.showSettings()">Settings</button>
        <button onclick="authUI.signOut()">Sign out</button>
      </div>
    `;
  }

  showSignIn() {
    const modal = document.createElement('div');
    modal.className = 'auth-modal';
    modal.innerHTML = `
      <div class="modal-content">
        <h2>Sign in to Relay</h2>

        <div class="sign-in-options">
          <div class="magic-link">
            <input
              type="email"
              id="email-input"
              placeholder="your@email.com"
              onkeypress="if(event.key==='Enter') authUI.sendMagicLink()"
            />
            <button onclick="authUI.sendMagicLink()">
              Send Magic Link
            </button>
          </div>

          <div class="divider">or</div>

          <button class="oauth-button google" onclick="authUI.signInWithGoogle()">
            Sign in with Google
          </button>

          <button class="oauth-button github" onclick="authUI.signInWithGitHub()">
            Sign in with GitHub
          </button>
        </div>

        <p class="benefits">
          ✓ Save conversation history<br>
          ✓ Unlimited messages<br>
          ✓ Use your own API keys<br>
          ✓ Access from any device
        </p>

        <button class="close" onclick="this.parentElement.parentElement.remove()">
          Continue anonymously
        </button>
      </div>
    `;

    document.body.appendChild(modal);
  }

  async sendMagicLink() {
    const email = document.getElementById('email-input').value;
    if (!email) return;

    try {
      const result = await this.auth.signInWithMagicLink(email);
      alert(result.message);
      document.querySelector('.auth-modal')?.remove();
    } catch (error) {
      alert(error.message);
    }
  }

  async signInWithGoogle() {
    try {
      await this.auth.signInWithGoogle();
    } catch (error) {
      alert(error.message);
    }
  }
}
```

### 5. Security Headers & CSRF Protection
```javascript
class SecurityMiddleware {
  static applyHeaders(response) {
    // Security headers (in addition to FastAPI)
    response.headers.set('X-Content-Type-Options', 'nosniff');
    response.headers.set('X-Frame-Options', 'DENY');
    response.headers.set('X-XSS-Protection', '1; mode=block');
    response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');

    return response;
  }

  static generateCSRFToken() {
    const token = crypto.randomUUID();
    sessionStorage.setItem('csrf_token', token);
    return token;
  }

  static validateCSRFToken(token) {
    const stored = sessionStorage.getItem('csrf_token');
    return token === stored;
  }

  static async secureRequest(url, options = {}) {
    const csrfToken = this.generateCSRFToken();

    const secureOptions = {
      ...options,
      headers: {
        ...options.headers,
        'X-CSRF-Token': csrfToken,
        'X-Requested-With': 'XMLHttpRequest'
      },
      credentials: 'same-origin'
    };

    const response = await fetch(url, secureOptions);
    return this.applyHeaders(response);
  }
}
```

## Database Schema for Auth
```sql
-- Supabase auth tables (managed by Supabase)
-- auth.users
-- auth.sessions

-- Custom tables
CREATE TABLE api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  provider VARCHAR(50) NOT NULL, -- 'openai', 'anthropic', etc.
  encrypted_key TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, provider)
);

CREATE TABLE user_data (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  migrated_history JSONB,
  migrated_at TIMESTAMPTZ,
  preferences JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id)
);

-- Row Level Security
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_data ENABLE ROW LEVEL SECURITY;

-- Users can only access their own data
CREATE POLICY api_keys_user_policy ON api_keys
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY user_data_policy ON user_data
  FOR ALL USING (auth.uid() = user_id);
```

## Testing
```javascript
describe('Authentication', () => {
  it('should handle anonymous sessions', () => {
    const session = new AnonymousSession();
    expect(session.sessionId).toMatch(/^anon_/);
    expect(session.canSendMessage().allowed).toBe(true);
  });

  it('should enforce rate limits', () => {
    const session = new AnonymousSession();

    // Send 20 messages
    for (let i = 0; i < 20; i++) {
      session.recordMessage();
    }

    const result = session.canSendMessage();
    expect(result.allowed).toBe(false);
    expect(result.reason).toBe('hourly_limit');
  });

  it('should encrypt API keys', async () => {
    const storage = new SecureKeyStorage();
    await storage.initializeEncryption('user123');

    const original = 'sk-test-key-12345';
    const encrypted = await storage.encryptApiKey(original);
    const decrypted = await storage.decryptApiKey(encrypted);

    expect(decrypted).toBe(original);
    expect(encrypted).not.toBe(original);
  });
});
```

## References
- [Supabase Auth Docs](https://supabase.com/docs/guides/auth)
- [Web Crypto API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API)
- ROADMAP.md auth decisions
- Sprint 61b requirements
