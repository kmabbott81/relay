'use client';

import { useState, useEffect } from 'react';
import { createClient } from '@supabase/supabase-js';

// Force dynamic rendering for this page (user-specific content)
export const dynamic = 'force-dynamic';

// Initialize Supabase client
const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co',
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'placeholder_key'
);

export default function BetaDashboard() {
  const [user, setUser] = useState<any>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [usage, setUsage] = useState({ today: 0, limit: 100 });

  useEffect(() => {
    checkUser();
    if (user) {
      loadFiles();
      loadUsage();
    }
  }, [user]);

  async function checkUser() {
    const { data: { session } } = await supabase.auth.getSession();
    setUser(session?.user ?? null);
    setLoading(false);
  }

  async function signInWithEmail(email: string) {
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: window.location.origin + '/beta'
      }
    });
    if (!error) {
      alert('Check your email for the login link!');
    }
  }

  async function signOut() {
    await supabase.auth.signOut();
    setUser(null);
  }

  async function loadFiles() {
    const { data } = await supabase
      .from('files')
      .select('*')
      .order('created_at', { ascending: false });
    setFiles(data || []);
  }

  async function loadUsage() {
    const { data } = await supabase
      .from('profiles')
      .select('usage_today, usage_limit')
      .single();
    if (data) {
      setUsage({ today: data.usage_today, limit: data.usage_limit });
    }
  }

  async function uploadFile(event: React.ChangeEvent<HTMLInputElement>) {
    if (!event.target.files || !event.target.files[0]) return;

    setUploading(true);
    const file = event.target.files[0];

    try {
      // Upload to Supabase Storage
      const fileExt = file.name.split('.').pop();
      const fileName = `${user.id}/${Date.now()}.${fileExt}`;

      const { error: uploadError } = await supabase.storage
        .from('user-files')
        .upload(fileName, file);

      if (uploadError) throw uploadError;

      // Save file record
      const { error: dbError } = await supabase
        .from('files')
        .insert({
          user_id: user.id,
          filename: file.name,
          content_type: file.type,
          size_bytes: file.size,
          storage_path: fileName
        });

      if (dbError) throw dbError;

      // Process file for embeddings (call your API)
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/knowledge/index`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${(await supabase.auth.getSession()).data.session?.access_token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ file_path: fileName })
      });

      if (!response.ok) throw new Error('Failed to process file');

      await loadFiles();
      alert('File uploaded and indexed successfully!');
    } catch (error) {
      console.error('Upload error:', error);
      alert('Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  }

  async function search() {
    if (!query.trim() || usage.today >= usage.limit) return;

    setSearching(true);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/knowledge/search`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${(await supabase.auth.getSession()).data.session?.access_token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ query, limit: 10 })
      });

      const data = await response.json();
      setResults(data.results || []);
      setUsage(prev => ({ ...prev, today: prev.today + 1 }));
    } catch (error) {
      console.error('Search error:', error);
      alert('Search failed. Please try again.');
    } finally {
      setSearching(false);
    }
  }

  async function sendFeedback(type: string, message: string) {
    await supabase
      .from('feedback')
      .insert({
        user_id: user?.id,
        type,
        message
      });
    alert('Thank you for your feedback!');
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-600"></div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-brand-50 to-blue-50 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-lg shadow-xl p-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Relay AI Beta</h1>
          <p className="text-gray-600 mb-6">Enter your email to access the private beta</p>

          <form onSubmit={(e) => {
            e.preventDefault();
            const email = (e.target as any).email.value;
            signInWithEmail(email);
          }}>
            <input
              type="email"
              name="email"
              placeholder="you@company.com"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg mb-4"
              required
            />
            <button
              type="submit"
              className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold py-2 px-4 rounded-lg"
            >
              Access Beta
            </button>
          </form>

          <p className="text-xs text-gray-500 mt-4 text-center">
            Beta access is invite-only. Contact kyle@relay.ai for access.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Relay AI Beta</h1>
              <p className="text-sm text-gray-600">Welcome, {user.email}</p>
            </div>

            <div className="flex items-center space-x-4">
              <div className="text-sm text-gray-600">
                Usage: <span className="font-bold">{usage.today}/{usage.limit}</span> queries today
              </div>
              <button
                onClick={signOut}
                className="text-sm text-gray-600 hover:text-gray-900"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid md:grid-cols-2 gap-8">
          {/* Upload Section */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Knowledge Base</h2>

            <div className="mb-6">
              <label className="block w-full">
                <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-brand-500 transition cursor-pointer">
                  <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="mt-2 text-sm text-gray-600">
                    {uploading ? 'Uploading...' : 'Click to upload PDF, TXT, or DOCX'}
                  </p>
                </div>
                <input
                  type="file"
                  className="hidden"
                  accept=".pdf,.txt,.docx"
                  onChange={uploadFile}
                  disabled={uploading}
                />
              </label>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-700">Your Files</h3>
              {files.length === 0 ? (
                <p className="text-sm text-gray-500">No files uploaded yet</p>
              ) : (
                <div className="max-h-48 overflow-y-auto">
                  {files.map((file) => (
                    <div key={file.id} className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded">
                      <span className="text-sm text-gray-700 truncate">{file.filename}</span>
                      <span className="text-xs text-gray-500">
                        {(file.size_bytes / 1024).toFixed(1)} KB
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Search Section */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">AI Search</h2>

            <form onSubmit={(e) => {
              e.preventDefault();
              search();
            }} className="mb-6">
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Ask anything about your documents..."
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg"
                  disabled={usage.today >= usage.limit}
                />
                <button
                  type="submit"
                  disabled={searching || !query.trim() || usage.today >= usage.limit}
                  className="px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {searching ? 'Searching...' : 'Search'}
                </button>
              </div>

              {usage.today >= usage.limit && (
                <p className="text-sm text-red-600 mt-2">Daily query limit reached. Resets at midnight.</p>
              )}
            </form>

            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-700">Results</h3>
              {results.length === 0 ? (
                <p className="text-sm text-gray-500">No results yet. Try searching!</p>
              ) : (
                <div className="max-h-64 overflow-y-auto space-y-3">
                  {results.map((result, i) => (
                    <div key={i} className="p-3 bg-gray-50 rounded">
                      <p className="text-sm text-gray-700">{result.text}</p>
                      <p className="text-xs text-gray-500 mt-1">
                        From: {result.filename} | Score: {result.score.toFixed(2)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Feedback Section */}
        <div className="mt-8 bg-brand-50 border border-brand-200 rounded-lg p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">Beta Feedback</h2>
          <p className="text-sm text-gray-600 mb-4">
            This is a beta product. Your feedback helps us improve!
          </p>

          <div className="flex space-x-2">
            <button
              onClick={() => {
                const msg = prompt('What bug did you find?');
                if (msg) sendFeedback('bug', msg);
              }}
              className="px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200"
            >
              🐛 Report Bug
            </button>
            <button
              onClick={() => {
                const msg = prompt('What feature would you like?');
                if (msg) sendFeedback('feature', msg);
              }}
              className="px-4 py-2 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200"
            >
              💡 Request Feature
            </button>
            <button
              onClick={() => {
                const msg = prompt('Any other feedback?');
                if (msg) sendFeedback('general', msg);
              }}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
            >
              💬 General Feedback
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
