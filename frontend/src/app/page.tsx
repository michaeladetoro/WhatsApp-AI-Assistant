'use client';
import { useState, useEffect, useRef } from 'react';
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer } from 'recharts';
import styles from './page.module.css';

interface KBDocument {
  id: string;
  filename: string;
  upload_date?: string;
  size?: number;
}

interface ChartData {
  date: string;
  day_label: string;
  count: number;
}

interface AnalyticsData {
  total_messages: number;
  unique_users: number;
  total_documents: number;
  chart_data?: ChartData[];
}

export default function Dashboard() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [activeTab, setActiveTab] = useState<'dashboard' | 'knowledge'>('dashboard');
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsData>({ total_messages: 0, unique_users: 0, total_documents: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark';
    if (savedTheme) {
      setTheme(savedTheme);
      document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setTheme('dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    }
    
    fetchDocuments();
    fetchAnalytics();
  }, []);

  useEffect(() => {
    if (activeTab === 'dashboard') {
      fetchAnalytics();
    }
  }, [activeTab]);

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
  };

  const fetchAnalytics = async () => {
    try {
      const res = await fetch('/api/kb/analytics');
      if (res.ok) {
        const data = await res.json();
        setAnalytics(data);
      }
    } catch (err) {
      console.error('Failed to fetch analytics', err);
    }
  };

  const fetchDocuments = async () => {
    setIsLoading(true);
    try {
      const res = await fetch('/api/kb/status');
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch documents', err);
    }
    setIsLoading(false);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsLoading(true);
    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch('/api/kb/ingest', {
          method: 'POST',
          body: formData,
        });

        if (res.ok) {
          successCount++;
        } else {
          failCount++;
        }
      } catch (err) {
        failCount++;
      }
    }

    setIsLoading(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    
    if (failCount === 0) {
      alert(`Successfully uploaded ${successCount} document(s)!`);
    } else {
      alert(`Uploaded ${successCount} document(s), but ${failCount} failed.`);
    }
    
    fetchDocuments();
    fetchAnalytics();
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this document?')) return;
    
    try {
      setIsLoading(true);
      const res = await fetch(`/api/kb/${id}`, { method: 'DELETE' });
      if (res.ok) {
        fetchDocuments();
        fetchAnalytics();
      } else {
        alert('Failed to delete document');
      }
    } catch (err) {
      alert('Error deleting document');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRename = async (id: string, currentName: string) => {
    const newName = prompt('Enter new filename:', currentName);
    if (!newName || newName === currentName) return;

    try {
      setIsLoading(true);
      const res = await fetch(`/api/kb/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: newName }),
      });
      if (res.ok) {
        fetchDocuments();
      } else {
        alert('Failed to rename document');
      }
    } catch (err) {
      alert('Error renaming document');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSystemAction = async (action: 'rebuild' | 'wipe_memory' | 'wipe_knowledge') => {
    const messages = {
      rebuild: 'Rebuild the vector index?',
      wipe_memory: 'Wipe all user chat memory? This cannot be undone.',
      wipe_knowledge: 'WARNING: Wipe ALL knowledge? This deletes all documents.',
    };

    if (!confirm(messages[action])) return;

    try {
      setIsLoading(true);
      const res = await fetch('/api/kb/system', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });

      if (res.ok) {
        alert('Action completed successfully!');
        fetchDocuments();
        fetchAnalytics();
      } else {
        alert('Action failed.');
      }
    } catch (err) {
      alert('Action failed due to network error.');
    } finally {
      setIsLoading(false);
    }
  };



  const fakeCounts = [12, 18, 15, 25, 22, 30, 28];
  const skeletonData = analytics.chart_data?.map((d, i) => ({ ...d, count: fakeCounts[i] })) || [];

  return (
    <div className={styles.dashboardContainer}>
      <aside className={styles.sidebar}>
        <div className={styles.brand} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div className={styles.brandIcon}>O</div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
            <span className="text-gradient" style={{ lineHeight: 1 }}>OmniChat</span>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px', letterSpacing: '0.05em', fontWeight: 600 }}>by Burlux</span>
          </div>
        </div>
        
        <nav className={styles.navLinks}>
          <div 
            className={`${styles.navLink} ${activeTab === 'dashboard' ? styles.active : ''}`}
            onClick={() => setActiveTab('dashboard')}
            style={{ cursor: 'pointer' }}
          >
            <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path></svg>
            Dashboard
          </div>
          <div 
            className={`${styles.navLink} ${activeTab === 'knowledge' ? styles.active : ''}`}
            onClick={() => setActiveTab('knowledge')}
            style={{ cursor: 'pointer' }}
          >
            <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
            Knowledge Base
          </div>
        </nav>
      </aside>

      <main className={styles.mainContent}>
        <header className={`${styles.header} animate-fade-in`}>
          <div>
            <h1>{activeTab === 'dashboard' ? 'Overview' : 'Knowledge Base'}</h1>
            <p className={styles.headerSubtitle}>
              {activeTab === 'dashboard' ? 'Manage your WhatsApp AI memory and resources.' : 'Manage documents ingested into the vector index.'}
            </p>
          </div>
          <div className={styles.headerActions}>
            <button onClick={toggleTheme} className={styles.themeToggle} title="Toggle Theme" aria-label="Toggle Theme">
              {theme === 'light' ? (
                <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path></svg>
              ) : (
                <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
              )}
            </button>
            <input 
              type="file" 
              ref={fileInputRef} 
              style={{ display: 'none' }} 
              onChange={handleFileUpload} 
              accept=".pdf,.txt,.docx,.xlsx,.png,.jpg,.jpeg"
              multiple
            />
            {activeTab === 'knowledge' && (
              <button onClick={() => fileInputRef.current?.click()} className={styles.primaryBtn} disabled={isLoading}>
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg>
                {isLoading ? 'Processing...' : 'Upload Document'}
              </button>
            )}
          </div>
        </header>

        {activeTab === 'dashboard' && (
          <section className={`${styles.analyticsSection} animate-fade-in delay-1`}>
            {/* Top Stats */}
            <div className={styles.statsGrid}>
              <div className={`${styles.statCard} glass-panel`}>
                <span className={styles.statLabel}>Unique Users</span>
                <span className={styles.statValue}>{analytics.unique_users}</span>
              </div>
              <div className={`${styles.statCard} glass-panel`}>
                <span className={styles.statLabel}>Unique User Knowledge Assets</span>
                <span className={styles.statValue}>{analytics.total_messages}</span>
              </div>
              <div className={`${styles.statCard} glass-panel`}>
                <span className={styles.statLabel}>Knowledge Assets (Documents)</span>
                <span className={styles.statValue}>{analytics.total_documents}</span>
              </div>
            </div>

            {/* Visual Chart */}
            <div className={`${styles.chartContainer} glass-panel`}>
              <h2 className={styles.chartHeader}>Message Volume (Last 7 Days)</h2>
              <div className={styles.chartArea} style={{ position: 'relative', width: '100%', height: '100%', padding: 0, border: 'none' }}>
                {analytics.chart_data && analytics.chart_data.length > 0 ? (
                  analytics.chart_data.reduce((sum, d) => sum + d.count, 0) === 0 ? (
                    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
                      <div className={styles.skeletonChart} style={{ width: '100%', height: '100%' }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={skeletonData} margin={{ top: 20, right: 10, left: 10, bottom: 0 }}>
                            <XAxis dataKey="day_label" stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                            <Bar dataKey="count" fill="var(--text-muted)" radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                      <div className={styles.emptyStateOverlay}>No Messages Yet</div>
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={analytics.chart_data} margin={{ top: 20, right: 10, left: 10, bottom: 0 }}>
                        <XAxis dataKey="day_label" stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: '8px', backdropFilter: 'blur(10px)' }}
                          itemStyle={{ color: 'var(--accent-primary)', fontWeight: 'bold' }}
                          formatter={(value) => [`${value} messages`, 'Volume']}
                          cursor={{ fill: 'rgba(255, 255, 255, 0.05)' }}
                        />
                        <Bar dataKey="count" fill="var(--accent-primary)" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )
                ) : (
                  <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                    No data available (Restart backend to sync)
                  </div>
                )}
              </div>
            </div>

            {/* Quick Actions Panel */}
            <h2 className={styles.chartHeader} style={{ marginTop: '1rem' }}>Quick Actions</h2>
            <div className={styles.quickActionsGrid}>
              <div className={`${styles.actionCard} glass-panel`} onClick={() => fileInputRef.current?.click()}>
                <div className={styles.actionIcon}>
                  <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg>
                </div>
                <div>
                  <h3 className={styles.actionTitle}>Teach AI</h3>
                  <p className={styles.actionDesc}>Upload new PDFs, images, or documents.</p>
                </div>
              </div>
              
              <div className={`${styles.actionCard} glass-panel`} onClick={() => setActiveTab('knowledge')}>
                <div className={styles.actionIcon}>
                  <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                </div>
                <div>
                  <h3 className={styles.actionTitle}>Manage Knowledge</h3>
                  <p className={styles.actionDesc}>Review, rename, or delete existing documents.</p>
                </div>
              </div>

              <div className={`${styles.actionCard} glass-panel ${styles.danger}`} onClick={() => handleSystemAction('wipe_memory')}>
                <div className={styles.actionIcon}>
                  <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                </div>
                <div>
                  <h3 className={styles.actionTitle}>Clear Memory</h3>
                  <p className={styles.actionDesc}>Wipe all user chat history permanently.</p>
                </div>
              </div>
            </div>
            
            <div className={styles.ttlNotice}>
              <strong>Privacy Policy Enforced:</strong> All user chat history (Unique User Knowledge Assets) has a strict <strong>4-hour Time-To-Live (TTL) limit</strong>. Messages older than 4 hours are automatically purged from the database.
            </div>
          </section>
        )}

        {activeTab === 'knowledge' && (
          <section className={`${styles.documentsSection} animate-fade-in delay-1`}>
            <div className={styles.documentsHeader}>
              <h2>Uploaded Documents</h2>
              <div style={{ display: 'flex', gap: '1rem' }}>
                <button onClick={() => handleSystemAction('rebuild')} className={styles.dangerBtn} style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }} disabled={isLoading}>
                  Rebuild Index
                </button>
                <button onClick={() => handleSystemAction('wipe_knowledge')} className={styles.dangerBtn} style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }} disabled={isLoading}>
                  Wipe ALL Knowledge
                </button>
              </div>
            </div>
            
            <div className={styles.docList}>
              {documents.length === 0 && !isLoading && (
                <p style={{ opacity: 0.5 }}>No documents uploaded yet. Upload a document to teach your AI.</p>
              )}
              
              {documents.map((doc, idx) => (
                <div key={doc.id || idx} className={`${styles.docItem} glass-panel`}>
                  <div className={styles.docInfo}>
                    <span className={styles.docTitle}>{doc.filename || doc.id}</span>
                    <span className={styles.docMeta}>
                      Document #{documents.length - idx}
                    </span>
                  </div>
                  <div className={styles.docActions}>
                    <button 
                      onClick={() => handleRename(doc.id, doc.filename || String(doc.id))} 
                      style={{ background: 'transparent', border: 'none', color: 'var(--text-main)', cursor: 'pointer', padding: '0.5rem', opacity: 0.7 }} 
                      disabled={isLoading} 
                      title="Rename Document"
                    >
                      <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                    </button>
                    <button onClick={() => handleDelete(doc.id)} className={styles.iconBtnDanger} disabled={isLoading} title="Delete Document">
                      <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
