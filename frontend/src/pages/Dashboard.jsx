import { useState, useEffect } from 'react'
import axios from 'axios'
import { Search, Bell, User, Settings, LogOut, Plus, BarChart2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import Chatbot from '../components/Chatbot'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5000'

function Dashboard() {
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedAccountId, setSelectedAccountId] = useState(null)
  const [accountDetails, setAccountDetails] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const [showProfile, setShowProfile] = useState(false)
  const [showNotifications, setShowNotifications] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [userName, setUserName] = useState('Alex Strategist')
  const [approveStatus, setApproveStatus] = useState(null);
  const [approving, setApproving] = useState(false);
  const [outcomeMarked, setOutcomeMarked] = useState(null);
  const [similarCases, setSimilarCases] = useState([]);
  const [loadingSimilar, setLoadingSimilar] = useState(false);
  const [dataSource, setDataSource] = useState(null);
  const [showSourceSelector, setShowSourceSelector] = useState(true);
  const selectedAccount = accountDetails;
  const setSelectedAccount = setAccountDetails;
  const [notifications, setNotifications] = useState([]);

  useEffect(() => {
    const savedName = localStorage.getItem('user_name');
    if (savedName) setUserName(savedName);
  }, []);

  useEffect(() => {
    if (dataSource) {
      fetchAccounts();
    }
  }, [dataSource]);

  useEffect(() => {
    if (!accounts || accounts.length === 0) return;
    const realNotifications = [];
    const highRisk = accounts.filter(a => a.risk_tier === 'HIGH').slice(0, 3);
    highRisk.forEach((acc, i) => {
      realNotifications.push({
        id: i + 1,
        text: `Critical Risk detected for ${acc.name} — Score ${acc.risk_score || ''}`,
        time: 'Just now',
        type: 'error'
      });
    });
    const contacted = accounts.filter(a => a.status === 'Contacted').slice(0, 2);
    contacted.forEach((acc, i) => {
      realNotifications.push({
        id: highRisk.length + i + 1,
        text: `Outreach approved for ${acc.name} — awaiting outcome`,
        time: 'Today',
        type: 'success'
      });
    });
    setNotifications(realNotifications);
  }, [accounts]);

  const filteredAccounts = accounts.filter(acc =>
    acc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    acc.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    acc.assigned_csm.toLowerCase().includes(searchQuery.toLowerCase())
  )

  useEffect(() => {
    if (selectedAccountId) {
      fetchAccountDetails(selectedAccountId)
      setApproveStatus(null)
      setApproving(false)
      setOutcomeMarked(null)
    }
  }, [selectedAccountId])

  const fetchAccounts = async () => {
    try {
      const userRole = localStorage.getItem('user_role');
      const userNameVal = localStorage.getItem('user_name');
      const url = dataSource === 'hubspot'
        ? `${API_BASE}/accounts?source=hubspot`
        : `${API_BASE}/accounts`;
      const response = await axios.get(url);

      const tierOrder = { 'HIGH': 0, 'MEDIUM': 1, 'LOW': 2 };
      const sorted = [...response.data].sort((a, b) => {
        const aTier = tierOrder[a.risk_tier] ?? 3;
        const bTier = tierOrder[b.risk_tier] ?? 3;
        return aTier - bTier;
      });

      setAccounts(sorted)
      setLoading(false)
    } catch (error) {
      console.error("Error fetching accounts:", error)
      if (dataSource) setError("Failed to fetch accounts. Is the backend running?")
      setLoading(false)
    }
  }

  const fetchAccountDetails = async (id) => {
    setAccountDetails(null)
    setAnalysis(null)
    setSimilarCases([])
    try {
      const response = await axios.get(`${API_BASE}/accounts/${id}`)
      setAccountDetails(response.data)

      setLoadingSimilar(true);
      try {
        const simRes = await axios.get(`${API_BASE}/accounts/${id}/similar`);
        setSimilarCases(simRes.data.similar_cases || []);
      } catch (err) {
        setSimilarCases([]);
      } finally {
        setLoadingSimilar(false);
      }
    } catch (error) {
      console.error("Error fetching account details:", error)
    }
  }

  const runAIAnalysis = async () => {
    if (!selectedAccountId) return
    setAnalyzing(true)
    setAnalysis(null)
    try {
      const response = await axios.post(`${API_BASE}/analyze/${selectedAccountId}`)
      if (response.data.error) {
        setError(`AI Analysis Error: ${response.data.error}`)
      } else {
        setAnalysis(response.data)
      }
    } catch (error) {
      console.error("Analysis failed:", error)
      setError("AI Analysis failed. Check your GROQ_API_KEY in the backend .env file.")
    } finally {
      setAnalyzing(false)
    }
  }

  const getTierColor = (tier) => {
    switch (tier) {
      case 'HIGH': return 'bg-rose-500/10 text-rose-500 border-rose-500/20';
      case 'MEDIUM': return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
      case 'LOW': return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
      default: return 'bg-slate-50 text-slate-600 border-slate-200';
    }
  }

  const [isEditingProfile, setIsEditingProfile] = useState(false)
  const [editName, setEditName] = useState(userName)
  const [isSavingSettings, setIsSavingSettings] = useState(false)
  const [systemSettings, setSystemSettings] = useState([
    { id: 'auto_ai', label: 'Auto-Trigger AI Analysis', desc: 'Automatically run reasoning agent on new ticket detection.', active: true },
    { id: 'slack', label: 'Slack Notifications', desc: 'Send critical risk alerts to #retention-war-room.', active: true },
    { id: 'sensitivity', label: 'High Sensitivity Mode', desc: 'Alert on 10% usage drop instead of 25%.', active: false },
    { id: 'beta', label: 'Beta Features', desc: 'Access upcoming predictive churn models.', active: false },
  ])

  const handleUpdateProfile = () => {
    localStorage.setItem('user_name', editName);
    setUserName(editName);
    setIsEditingProfile(false);
  };

  const toggleSetting = (id) => {
    setSystemSettings(prev => prev.map(s =>
      s.id === id ? { ...s, active: !s.active } : s
    ));
  };

  const handleSaveSettings = () => {
    setIsSavingSettings(true);
    setTimeout(() => {
      setIsSavingSettings(false);
      setShowSettings(false);
    }, 1200);
  };

  const [newAcc, setNewAcc] = useState({
    id: '', name: '', assigned_csm: userName, monthly_charges: 0, tenure: 0, contract_type: 'Monthly', contract_value: 0
  })

  useEffect(() => {
    setNewAcc(prev => ({
      ...prev,
      contract_value: prev.monthly_charges * prev.tenure
    }));
  }, [newAcc.monthly_charges, newAcc.tenure]);

  const handleAddAccount = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API_BASE}/accounts`, {
        ...newAcc,
        monthly_charges: Number(newAcc.monthly_charges),
        tenure: Number(newAcc.tenure),
        contract_value: Number(newAcc.contract_value)
      });
      setShowAddModal(false);
      fetchAccounts();
      setNewAcc({ id: '', name: '', assigned_csm: userName, monthly_charges: 0, tenure: 0, contract_type: 'Monthly', contract_value: 0 });
    } catch (err) {
      setError(err.response?.data?.error || "Failed to add account");
    }
  }

  const handleApprove = async () => {
    if (!selectedAccount) return;
    setApproving(true);
    try {
      const outreachMessage = analysis?.outreach_draft || '';
      const csmName = localStorage.getItem('user_name') || 'CSM';
      const res = await axios.post(`${API_BASE}/accounts/${selectedAccount.id}/approve`, {
        outreach_message: outreachMessage,
        csm_name: csmName,
        account_name: selectedAccount.name || ''
      });
      setApproveStatus('success');
      setSelectedAccount(prev => ({ ...prev, status: 'Contacted' }));
      setAccounts(prev => prev.map(a => a.id === selectedAccount.id ? { ...a, status: 'Contacted' } : a));
      if (res.data.hubspot_sent) {
        console.log('[Approve] Message logged to HubSpot successfully.');
      }
    } catch (err) {
      setApproveStatus('error');
    } finally {
      setApproving(false);
    }
  };

  const handleMarkRenewed = async () => {
    if (!selectedAccount) return;
    try {
      await axios.post(`${API_BASE}/accounts/${selectedAccount.id}/renew`);
      setOutcomeMarked('renewed');
    } catch (err) {
      console.error('Mark renewed error:', err);
    }
  };

  const handleMarkChurned = async () => {
    if (!selectedAccount) return;
    try {
      await axios.post(`${API_BASE}/accounts/${selectedAccount.id}/outcome`, {
        outcome: 'churned',
        csm_action: 'CSM marked as churned'
      });
      setOutcomeMarked('churned');
    } catch (err) {
      console.error('Mark churned error:', err);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-900 font-sans selection:bg-indigo-100 font-display">
      {showSourceSelector && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.7)',
          backdropFilter: 'blur(8px)', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '24px'
        }}>
          <div style={{
            background: '#ffffff', borderRadius: '32px',
            padding: '48px', maxWidth: '520px', width: '100%',
            boxShadow: '0 32px 64px rgba(0,0,0,0.2)'
          }}>
            <div style={{ textAlign: 'center', marginBottom: '32px' }}>
              <div style={{
                width: 64, height: 64, background: '#eef2ff',
                borderRadius: 20, display: 'flex', alignItems: 'center',
                justifyContent: 'center', margin: '0 auto 16px',
                fontSize: 28
              }}>⚡</div>
              <h2 style={{
                fontSize: 24, fontWeight: 900, color: '#0f172a',
                marginBottom: 8, letterSpacing: '-0.5px'
              }}>Select Data Source</h2>
              <p style={{ fontSize: 14, color: '#64748b', fontWeight: 500 }}>
                Choose where to load your customer accounts from
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <button
                type="button"
                onClick={() => { setDataSource('hubspot'); setShowSourceSelector(false); localStorage.setItem('analytics_source', 'hubspot'); }}
                style={{
                  padding: '20px 24px', background: '#fff',
                  border: '2px solid #e2e8f0', borderRadius: 20,
                  cursor: 'pointer', textAlign: 'left', transition: 'all 0.2s',
                  display: 'flex', alignItems: 'center', gap: 16
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = '#6366f1'; e.currentTarget.style.background = '#eef2ff'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.background = '#fff'; }}
              >
                <div style={{
                  width: 48, height: 48, background: '#ff7a59',
                  borderRadius: 14, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', fontSize: 22, flexShrink: 0
                }}>🔗</div>
                <div>
                  <p style={{ fontSize: 15, fontWeight: 800, color: '#0f172a', margin: '0 0 4px 0' }}>
                    HubSpot CRM
                  </p>
                  <p style={{ fontSize: 12, color: '#64748b', fontWeight: 500, margin: 0 }}>
                    Live data from your HubSpot account — 30 real companies with full risk signals
                  </p>
                </div>
                <div style={{
                  marginLeft: 'auto', padding: '4px 10px',
                  background: '#dcfce7', color: '#16a34a',
                  borderRadius: 8, fontSize: 10, fontWeight: 800,
                  textTransform: 'uppercase', letterSpacing: '0.05em', flexShrink: 0
                }}>Live</div>
              </button>

              <button
                type="button"
                onClick={() => { setDataSource('csv'); setShowSourceSelector(false); localStorage.setItem('analytics_source', 'csv'); }}
                style={{
                  padding: '20px 24px', background: '#fff',
                  border: '2px solid #e2e8f0', borderRadius: 20,
                  cursor: 'pointer', textAlign: 'left', transition: 'all 0.2s',
                  display: 'flex', alignItems: 'center', gap: 16
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = '#6366f1'; e.currentTarget.style.background = '#eef2ff'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.background = '#fff'; }}
              >
                <div style={{
                  width: 48, height: 48, background: '#6366f1',
                  borderRadius: 14, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', fontSize: 22, flexShrink: 0
                }}>📊</div>
                <div>
                  <p style={{ fontSize: 15, fontWeight: 800, color: '#0f172a', margin: '0 0 4px 0' }}>
                    CSV Demo Data
                  </p>
                  <p style={{ fontSize: 12, color: '#64748b', fontWeight: 500, margin: 0 }}>
                    Synthetic demo accounts — 31 accounts for testing and demonstration
                  </p>
                </div>
                <div style={{
                  marginLeft: 'auto', padding: '4px 10px',
                  background: '#f1f5f9', color: '#64748b',
                  borderRadius: 8, fontSize: 10, fontWeight: 800,
                  textTransform: 'uppercase', letterSpacing: '0.05em', flexShrink: 0
                }}>Demo</div>
              </button>
            </div>

            <p style={{
              textAlign: 'center', fontSize: 11, color: '#94a3b8',
              marginTop: 20, fontWeight: 500
            }}>
              You can switch data sources anytime from the dashboard header
            </p>
          </div>
        </div>
      )}
      {/* Dynamic Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-500/5 blur-[120px] rounded-full animate-pulse"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-500/5 blur-[120px] rounded-full animate-pulse delay-700"></div>
      </div>

      <div className="relative max-w-[1600px] mx-auto p-6 lg:p-10">
        <header className="flex flex-col lg:flex-row justify-between items-center mb-12 gap-8">
          <div className="flex items-center gap-10 w-full lg:w-auto">
            <Link to="/" className="flex items-center gap-3 group">
              <div className="w-12 h-12 bg-indigo-600 rounded-2xl flex items-center justify-center shadow-xl shadow-indigo-200 group-hover:scale-110 transition-transform">
                <span className="text-2xl font-black text-white italic">C</span>
              </div>
              <div>
                <h1 className="text-2xl font-black tracking-tighter text-slate-900 leading-none mb-1">
                  ChurnAlert <span className="text-indigo-600">AI</span>
                </h1>
                <p className="text-[10px] text-slate-400 font-black uppercase tracking-[0.2em]">Customer Retention Workflow</p>
              </div>
            </Link>

            <button
              type="button"
              onClick={() => setShowSourceSelector(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 14px',
                background: dataSource === 'hubspot' ? '#fff7ed' : '#eef2ff',
                border: `1px solid ${dataSource === 'hubspot' ? '#fed7aa' : '#c7d2fe'}`,
                borderRadius: 12,
                cursor: 'pointer',
                fontSize: 11,
                fontWeight: 800,
                color: dataSource === 'hubspot' ? '#ea580c' : '#6366f1',
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}
            >
              {dataSource === 'hubspot' ? '🔗 HubSpot' : '📊 CSV Demo'}
            </button>

            <div className="hidden xl:flex items-center bg-white border border-slate-100 rounded-2xl px-4 py-2 w-96 shadow-sm focus-within:ring-2 focus-within:ring-indigo-100 focus-within:border-indigo-400 transition-all">
              <Search className="w-4 h-4 text-slate-400 mr-3" />
              <input
                type="text"
                placeholder="Search accounts, CSMs, or tickets..."
                className="bg-transparent border-none outline-none text-sm font-medium text-slate-600 w-full"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-black text-slate-400 bg-slate-50 border border-slate-200 rounded ml-2">⌘K</kbd>
            </div>
          </div>

          <div className="flex items-center gap-6 w-full lg:w-auto justify-between lg:justify-end">
            <div className="flex gap-3">
              <Link to="/analytics" title="View Analytics" className="p-3 bg-white border border-slate-100 shadow-sm rounded-2xl text-slate-400 hover:text-indigo-600 hover:border-indigo-100 transition-all flex flex-col items-center gap-0.5">
                <BarChart2 className="w-5 h-5" />
                <span className="text-[8px] font-black uppercase tracking-wider">Analytics</span>
              </Link>
              <div className="px-5 py-2.5 bg-white border border-slate-100 shadow-sm rounded-2xl text-center min-w-[100px]">
                <p className="text-[9px] text-slate-400 uppercase font-black tracking-widest mb-0.5">Portfolio</p>
                <p className="text-lg font-black text-slate-800 leading-none">{accounts.length}</p>
              </div>
              <div className="px-5 py-2.5 bg-rose-50 border border-rose-100 shadow-sm rounded-2xl text-center min-w-[100px]">
                <p className="text-[9px] text-rose-500 uppercase font-black tracking-widest mb-0.5">Critical</p>
                <p className="text-lg font-black text-rose-600 leading-none">{accounts.filter(a => a.risk_tier === 'HIGH').length}</p>
              </div>
            </div>

            <div className="h-10 w-[1px] bg-slate-200 hidden md:block"></div>

            <div className="flex items-center gap-4">
              <div className="relative">
                <button
                  onClick={() => setShowNotifications(!showNotifications)}
                  className={`p-3 rounded-xl transition-all relative ${showNotifications ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-indigo-600 hover:bg-indigo-50'}`}
                >
                  <Bell className="w-5 h-5" />
                  {notifications.length > 0 && (
                    <span className="absolute top-3 right-3 w-2 h-2 bg-rose-500 rounded-full border-2 border-white"></span>
                  )}
                </button>

                {showNotifications && (
                  <div className="absolute right-0 mt-3 w-80 bg-white border border-slate-100 rounded-3xl shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2">
                    <div className="p-4 border-b border-slate-50 flex justify-between items-center">
                      <p className="text-xs font-black uppercase tracking-widest text-slate-400">Notifications</p>
                      <button onClick={() => setNotifications([])} className="text-[10px] font-bold text-indigo-600">Clear All</button>
                    </div>
                    <div className="max-h-80 overflow-y-auto">
                      {notifications.length > 0 ? notifications.map(n => (
                        <div key={n.id} className="p-4 border-b border-slate-50 hover:bg-slate-50 transition-colors">
                          <p className="text-sm font-medium text-slate-800 mb-1">{n.text}</p>
                          <p className="text-[10px] text-slate-400 font-bold">{n.time}</p>
                        </div>
                      )) : (
                        <div className="p-8 text-center">
                          <p className="text-sm font-bold text-slate-300">All caught up!</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex items-center gap-3 pl-4 border-l border-slate-100">
                <div className="text-right hidden sm:block">
                  <p className="text-sm font-black text-slate-900 leading-none mb-1">{userName}</p>
                  <p className="text-[10px] text-indigo-600 font-bold uppercase tracking-wider">Senior CSM</p>
                </div>
                <div className="relative group">
                  <button className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 p-0.5 shadow-lg shadow-indigo-100 overflow-hidden">
                    <img
                      src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${userName}`}
                      alt="Avatar"
                      className="w-full h-full rounded-[14px] bg-white"
                    />
                  </button>

                  {/* Dropdown Menu */}
                  <div className="absolute right-0 mt-3 w-48 bg-white border border-slate-100 rounded-2xl shadow-2xl shadow-slate-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 p-2">
                    <button
                      onClick={() => setShowProfile(true)}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm font-bold text-slate-600 hover:bg-slate-50 rounded-xl transition-colors"
                    >
                      <User className="w-4 h-4" /> Profile
                    </button>
                    <button
                      onClick={() => setShowSettings(true)}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm font-bold text-slate-600 hover:bg-slate-50 rounded-xl transition-colors"
                    >
                      <Settings className="w-4 h-4" /> Settings
                    </button>
                    <div className="h-[1px] bg-slate-50 my-1 mx-2"></div>
                    <Link to="/" className="w-full flex items-center gap-3 px-4 py-3 text-sm font-bold text-rose-600 hover:bg-rose-50 rounded-xl transition-colors">
                      <LogOut className="w-4 h-4" /> Logout
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </header>

        {error && (
          <div className="mb-8 p-4 bg-rose-50 border border-rose-100 rounded-xl text-rose-700 text-sm flex items-center justify-between animate-in fade-in slide-in-from-top-2 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="text-lg">⚠️</span> {error}
            </div>
            <button onClick={() => setError(null)} className="opacity-50 hover:opacity-100 font-bold text-xl">×</button>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Account List Sidebar */}
          <div className="lg:col-span-4 flex flex-col gap-4 max-h-[850px]">
            <div className="flex justify-between items-center px-2">
              <h2 className="text-xs font-black uppercase tracking-widest text-slate-400">Portfolio Accounts</h2>
              <div className="flex gap-4">
                <button onClick={() => setShowAddModal(true)} className="text-indigo-600 hover:text-indigo-700 text-xs font-bold transition-colors flex items-center gap-1">
                  <Plus className="w-3 h-3" /> Add New
                </button>
                <button onClick={fetchAccounts} className="text-slate-400 hover:text-indigo-600 text-xs font-bold transition-colors">Refresh Feed</button>
              </div>
            </div>
            <div className="overflow-y-auto pr-2 space-y-3 custom-scrollbar">
              {loading ? (
                Array(5).fill(0).map((_, i) => (
                  <div key={i} className="h-24 bg-white animate-pulse rounded-2xl border border-slate-100 shadow-sm"></div>
                ))
              ) : filteredAccounts.length > 0 ? (
                filteredAccounts.map((acc) => (
                  <div
                    key={acc.id}
                    onClick={() => setSelectedAccountId(acc.id)}
                    className={`w-full text-left p-5 rounded-2xl transition-all duration-300 border relative overflow-hidden group ${selectedAccountId === acc.id
                      ? 'bg-white border-indigo-400 shadow-[0_10px_40px_-10px_rgba(79,70,229,0.15)] scale-[1.02] z-10'
                      : 'bg-white border-slate-100 hover:border-slate-300 hover:shadow-md'
                      }`}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="flex justify-between items-start mb-2 relative z-10">
                      <div>
                        <h3 className="font-bold text-slate-800 leading-tight mb-1 group-hover:text-indigo-600 transition-colors">{acc.name}</h3>
                        <p className="text-[10px] text-slate-400 font-mono tracking-tight">{acc.id}</p>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '2px' }}>
                        <div className={`px-2 py-0.5 rounded-lg text-[9px] font-black border ${getTierColor(acc.risk_tier)}`}>
                          {acc.risk_tier}
                        </div>
                        {acc.prev_risk_score !== null && acc.prev_risk_score !== undefined && acc.risk_score !== undefined && acc.risk_score !== acc.prev_risk_score && (
                          <span style={{
                            fontSize: '9px', fontWeight: 800,
                            color: acc.risk_score > acc.prev_risk_score ? '#dc2626' : '#16a34a'
                          }}>
                            {acc.risk_score > acc.prev_risk_score ? `↑ from ${Math.round(acc.prev_risk_score)}` : `↓ from ${Math.round(acc.prev_risk_score)}`}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex justify-between items-center text-[11px] text-slate-500 relative z-10">
                      <span>CSM: {acc.assigned_csm.split(' ')[0]}</span>
                      <span className="font-mono text-slate-700 font-bold">${acc.monthly_charges}/mo</span>
                    </div>
                    <div style={{ display: 'flex', gap: '6px', marginTop: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
                      {(() => {
                        if (acc.renewal_date) {
                          const days = Math.ceil((new Date(acc.renewal_date) - new Date()) / (1000 * 60 * 60 * 24));
                          if (days < 0) {
                            return <span style={{ fontSize: '9px', fontWeight: 800, background: '#fee2e2', color: '#b91c1c', padding: '2px 8px', borderRadius: '6px' }}>⚠️ Overdue {Math.abs(days)}d</span>;
                          } else if (days <= 30) {
                            return <span style={{ fontSize: '9px', fontWeight: 800, background: '#fef2f2', color: '#dc2626', padding: '2px 8px', borderRadius: '6px' }}>🔴 Renewal in {days}d</span>;
                          } else {
                            return <span style={{ fontSize: '9px', fontWeight: 700, background: '#f1f5f9', color: '#64748b', padding: '2px 8px', borderRadius: '6px' }}>📅 {acc.renewal_date.slice(0, 10)}</span>;
                          }
                        }
                        return null;
                      })()}
                      <span style={{
                        fontSize: '9px', fontWeight: 800, padding: '2px 8px', borderRadius: '6px',
                        background: acc.status === 'Contacted' ? '#f0fdf4' : acc.status === 'Churned' ? '#fef2f2' : '#f8fafc',
                        color: acc.status === 'Contacted' ? '#16a34a' : acc.status === 'Churned' ? '#dc2626' : '#94a3b8'
                      }}>
                        {acc.status === 'Contacted' ? '✅ Contacted' : acc.status === 'Churned' ? '❌ Churned' : '⏳ No Action'}
                      </span>
                    </div>
                    {acc.status !== 'Contacted' && acc.status !== 'Churned' && (
                      <button
                        onClick={async (e) => {
                          e.stopPropagation();
                          try {
                            await axios.post(`${API_BASE}/accounts/${acc.id}/approve`, {
                              outreach_message: 'Quick approval from dashboard',
                              csm_name: localStorage.getItem('user_name') || 'CSM',
                              account_name: acc.name || ''
                            });
                            setAccounts(prev => prev.map(a => a.id === acc.id ? { ...a, status: 'Contacted' } : a));
                          } catch (err) {
                            console.error('Quick approve error:', err);
                          }
                        }}
                        style={{
                          marginTop: '6px', width: '100%', padding: '6px',
                          background: '#1e293b', color: '#fff',
                          border: 'none', borderRadius: '10px',
                          fontSize: '10px', fontWeight: 800,
                          cursor: 'pointer', letterSpacing: '0.05em'
                        }}
                      >
                        ⚡ Quick Approve
                      </button>
                    )}
                    {selectedAccountId === acc.id && (
                      <div className="absolute top-0 right-0 w-1.5 h-full bg-indigo-500 animate-in slide-in-from-right-full duration-500"></div>
                    )}
                  </div>
                ))
              ) : (
                <div>
                  {filteredAccounts.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '40px 20px' }}>
                      {searchQuery ? (
                        <p style={{ color: '#94a3b8', fontWeight: 700, fontSize: '13px' }}>No accounts match your search.</p>
                      ) : (
                        <div>
                          <div style={{ fontSize: '32px', marginBottom: '12px' }}>🎉</div>
                          <p style={{ color: '#16a34a', fontWeight: 800, fontSize: '14px', marginBottom: '4px' }}>All accounts are healthy!</p>
                          <p style={{ color: '#94a3b8', fontWeight: 500, fontSize: '12px' }}>No at-risk accounts today.</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Detail & AI View */}
          <div className="lg:col-span-8 space-y-8 min-h-[850px]">
            {accountDetails ? (
              <div className="space-y-8 animate-in fade-in slide-in-from-right-6 duration-500">
                {/* Stats Row */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  {[
                    { label: 'Risk Score', val: accountDetails.risk_info.score, color: 'text-indigo-600' },
                    { label: 'Tenure', val: `${accountDetails.tenure}m`, color: 'text-slate-800' },
                    { label: 'Contract', val: accountDetails.contract_type, color: 'text-slate-800' },
                    { label: 'Value', val: `$${accountDetails.contract_value.toLocaleString()}`, color: 'text-emerald-600' },
                    { label: 'Renewal Date', val: accountDetails.renewal_date ? String(accountDetails.renewal_date).slice(0, 10) : 'N/A', color: 'text-rose-600' },
                    { label: 'Last Login', val: accountDetails.last_login_date ? String(accountDetails.last_login_date).slice(0, 10) : 'N/A', color: 'text-indigo-900' },
                  ].map((stat, i) => (
                    <div key={i} className="bg-white border border-slate-100 p-4 rounded-3xl shadow-sm">
                      <p className="text-[9px] text-slate-400 uppercase font-black tracking-widest mb-1">{stat.label}</p>
                      <p className={`text-base font-black ${stat.color} truncate`}>{stat.val}</p>
                    </div>
                  ))}
                </div>

                {/* Risk Factor Breakdown */}
                {accountDetails.risk_info && (
                  <div className="bg-white border border-slate-100 rounded-3xl shadow-sm p-6">
                    <div className="flex items-center justify-between mb-4">
                      <p className="text-xs text-slate-400 font-black uppercase tracking-widest">Risk Factor Breakdown</p>
                      <span className={`text-xs font-black px-3 py-1 rounded-full ${accountDetails.risk_info.tier === 'HIGH'
                        ? 'bg-red-50 text-red-600'
                        : accountDetails.risk_info.tier === 'MEDIUM'
                          ? 'bg-amber-50 text-amber-600'
                          : 'bg-emerald-50 text-emerald-600'
                        }`}>
                        {accountDetails.risk_info.tier} RISK — Score {accountDetails.risk_info.score}/100
                      </span>
                    </div>

                    {/* Score Bar */}
                    <div className="mb-5">
                      <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden">
                        <div
                          className={`h-3 rounded-full transition-all duration-700 ${accountDetails.risk_info.score >= 70
                            ? 'bg-gradient-to-r from-red-400 to-red-600'
                            : accountDetails.risk_info.score >= 35
                              ? 'bg-gradient-to-r from-amber-400 to-amber-600'
                              : 'bg-gradient-to-r from-emerald-400 to-emerald-600'
                            }`}
                          style={{ width: `${accountDetails.risk_info.score}%` }}
                        />
                      </div>
                      <div className="flex justify-between mt-1">
                        <span className="text-[10px] text-slate-400 font-medium">0</span>
                        <span className="text-[10px] text-slate-400 font-medium">100</span>
                      </div>
                    </div>

                    {/* Risk Reasons List */}
                    {accountDetails.risk_info.reasons && accountDetails.risk_info.reasons.length > 0 ? (
                      <div className="space-y-2">
                        <p className="text-[10px] text-slate-400 font-black uppercase tracking-widest mb-3">Triggered Risk Factors</p>
                        {accountDetails.risk_info.reasons.map((reason, i) => (
                          <div key={i} className="flex items-start gap-3 p-3 bg-slate-50 rounded-2xl border border-slate-100">
                            <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${accountDetails.risk_info.tier === 'HIGH'
                              ? 'bg-red-500'
                              : accountDetails.risk_info.tier === 'MEDIUM'
                                ? 'bg-amber-500'
                                : 'bg-emerald-500'
                              }`} />
                            <p className="text-sm text-slate-700 font-medium leading-snug">{reason}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="flex items-center gap-3 p-3 bg-emerald-50 rounded-2xl border border-emerald-100">
                        <div className="w-2 h-2 rounded-full bg-emerald-500 flex-shrink-0" />
                        <p className="text-sm text-emerald-700 font-medium">No risk factors triggered. Account is healthy.</p>
                      </div>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {/* Signals Panel */}
                  <div className="bg-white border border-slate-200 rounded-[32px] p-8 shadow-sm">
                    <h3 className="text-base font-black uppercase text-slate-500 mb-8 flex items-center gap-2 tracking-widest">
                      <span className="w-1.5 h-6 bg-indigo-500 rounded-full"></span>
                      Behavioral Signals
                    </h3>

                    <div className="space-y-10">
                      <div>
                        <div className="flex justify-between text-sm mb-3">
                          <span className="text-slate-500 font-bold">Feature Adoption Rate</span>
                          <span className="font-black text-indigo-600 text-lg">{accountDetails.usage_metrics[0]?.feature_adoption_pct.toFixed(0)}%</span>
                        </div>
                        <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden shadow-inner">
                          <div
                            className="h-full bg-gradient-to-r from-indigo-400 via-indigo-600 to-purple-600 transition-all duration-1000 shadow-[0_0_15px_rgba(99,102,241,0.2)]"
                            style={{ width: `${accountDetails.usage_metrics[0]?.feature_adoption_pct}%` }}
                          ></div>
                        </div>
                      </div>

                      <div className="pt-6 border-t border-slate-100">
                        <p className="text-xs text-slate-400 font-black uppercase mb-5 tracking-widest">Emotional Sentiment Feed</p>
                        <div className="space-y-3">
                          {accountDetails.support_tickets.slice(0, 3).map((t, i) => (
                            <TicketItem key={i} ticket={t} />
                          ))}
                        </div>
                      </div>

                      <div className="pt-6 border-t border-slate-100">
                        <p className="text-xs text-slate-400 font-black uppercase mb-4 tracking-widest text-center">AI Context Payload</p>
                        <div className="relative group">
                          <pre className="p-5 bg-slate-50 rounded-2xl border border-slate-100 text-[11px] font-mono text-slate-600 overflow-x-auto max-h-[180px] custom-scrollbar shadow-inner">
                            {JSON.stringify({
                              metrics: accountDetails.usage_metrics[0],
                              risk: accountDetails.risk_info,
                              account: { tenure: accountDetails.tenure, contract: accountDetails.contract_type }
                            }, null, 2)}
                          </pre>
                          <div className="absolute top-3 right-3 px-2 py-1 bg-white rounded text-[9px] font-black text-indigo-500 border border-slate-100 uppercase tracking-tighter shadow-sm opacity-0 group-hover:opacity-100 transition-opacity">
                            Verified Data
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* AI Agent Panel */}
                  <div className="bg-indigo-50/30 border border-indigo-100 rounded-[32px] p-8 shadow-sm flex flex-col relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 blur-3xl rounded-full translate-x-10 -translate-y-10"></div>

                    <h3 className="text-sm font-black uppercase text-indigo-600 mb-8 flex items-center gap-2 relative z-10">
                      <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse"></span>
                      AI Analysis Agent
                    </h3>

                    {!analysis ? (
                      <div className="flex-1 flex flex-col items-center justify-center text-center p-8 relative z-10">
                        <div className="w-24 h-24 bg-white shadow-xl shadow-indigo-100 rounded-3xl flex items-center justify-center mb-8 relative group">
                          <span className="text-4xl group-hover:scale-110 transition-transform duration-500">🤖</span>
                          <div className="absolute inset-0 border-2 border-indigo-100 rounded-3xl animate-ping opacity-20"></div>
                        </div>
                        <h4 className="text-slate-800 font-black text-xl mb-3 tracking-tight">Agent Standby</h4>
                        <p className="text-slate-500 text-sm leading-relaxed mb-10 max-w-[240px]">
                          Trigger the reasoning engine to synthesize behavioral signals into strategy.
                        </p>
                        <button
                          onClick={runAIAnalysis}
                          disabled={analyzing}
                          className="w-full py-5 bg-indigo-600 text-white rounded-3xl font-black hover:bg-indigo-700 transition-all shadow-xl shadow-indigo-100 disabled:opacity-50 active:scale-[0.98] text-sm uppercase tracking-widest"
                        >
                          {analyzing ? 'Synthesizing...' : 'Trigger Analysis'}
                        </button>
                      </div>
                    ) : (
                      <div className="space-y-8 animate-in zoom-in-[0.98] duration-500 relative z-10">
                        {analysis && analysis.confidence && (
                          <div className="mb-4 inline-flex items-center gap-1.5 px-3 py-1 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-lg text-xs font-black">
                            Confidence: {analysis.confidence}
                          </div>
                        )}
                        <div>
                          <p className="text-[10px] text-indigo-500 font-black uppercase tracking-widest mb-3">Churn Rationale</p>
                          <div className="p-6 bg-white rounded-[24px] border border-slate-100 shadow-sm text-sm text-slate-700 leading-relaxed italic border-l-4 border-l-indigo-500">
                            <div style={{ fontSize: '13px', color: '#334155', lineHeight: '1.8' }}>
                              {analysis.reasoning && analysis.reasoning.split('•').filter(r => r.trim()).map((reason, i) => (
                                <div key={i} style={{ display: 'flex', gap: '8px', marginBottom: '6px' }}>
                                  <span style={{ color: '#6366f1', fontWeight: 800, flexShrink: 0 }}>•</span>
                                  <span>{reason.trim()}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>

                        <div>
                          <p className="text-[10px] text-emerald-600 font-black uppercase tracking-widest mb-3">Prescribed Strategy</p>
                          <div className="flex items-center gap-4 p-5 bg-emerald-50 rounded-[24px] border border-emerald-100 text-emerald-700 font-black text-sm shadow-sm">
                            <span className="text-2xl bg-white w-10 h-10 flex items-center justify-center rounded-xl shadow-sm">🎯</span>
                            <div style={{ fontSize: '13px', color: '#065f46', lineHeight: '1.8' }}>
                              {analysis.action_recommendation && analysis.action_recommendation.split('•').filter(r => r.trim()).map((reason, i) => (
                                <div key={i} style={{ display: 'flex', gap: '8px', marginBottom: '6px' }}>
                                  <span style={{ color: '#059669', fontWeight: 800, flexShrink: 0 }}>•</span>
                                  <span>{reason.trim()}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>

                        <div>
                          <p className="text-[10px] text-slate-400 font-black uppercase tracking-widest mb-3">Generated Outreach</p>
                          <div className="relative group">
                            <textarea
                              className="w-full h-40 p-5 bg-slate-50 text-slate-600 text-[12px] rounded-3xl font-mono focus:ring-2 focus:ring-indigo-100 outline-none border border-slate-100 shadow-inner resize-none transition-all"
                              value={analysis.outreach_draft}
                              readOnly
                            />
                            <div className="absolute bottom-4 right-4 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button className="p-2 bg-white rounded-lg shadow-sm border border-slate-100 text-slate-400 hover:text-indigo-600">📋</button>
                            </div>
                          </div>
                        </div>

                        <button
                          onClick={handleApprove}
                          disabled={approving}
                          className="w-full py-5 bg-slate-900 text-white rounded-3xl font-black hover:bg-slate-800 transition-all shadow-xl shadow-slate-200 active:scale-[0.98] text-sm uppercase tracking-widest"
                        >
                          {approving ? 'Sending...' : approveStatus === 'success' ? 'Approved — Contacted' : 'Approve & Deploy'}
                        </button>
                        {approveStatus === 'success' && (
                          <div style={{ marginTop: '12px' }}>
                            <p style={{ color: '#16a34a', fontSize: '13px', fontWeight: 700, marginBottom: '12px', textAlign: 'center' }}>
                              ✅ Outreach approved and logged to HubSpot.
                            </p>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                              <button
                                onClick={handleMarkRenewed}
                                disabled={outcomeMarked}
                                style={{
                                  padding: '12px', background: outcomeMarked === 'renewed' ? '#dcfce7' : '#f0fdf4',
                                  border: '2px solid #16a34a', borderRadius: '16px',
                                  color: '#16a34a', fontWeight: 800, fontSize: '12px',
                                  cursor: outcomeMarked ? 'not-allowed' : 'pointer',
                                  opacity: outcomeMarked && outcomeMarked !== 'renewed' ? 0.4 : 1
                                }}
                              >
                                ✅ Mark as Renewed
                              </button>
                              <button
                                onClick={handleMarkChurned}
                                disabled={outcomeMarked}
                                style={{
                                  padding: '12px', background: outcomeMarked === 'churned' ? '#fee2e2' : '#fef2f2',
                                  border: '2px solid #dc2626', borderRadius: '16px',
                                  color: '#dc2626', fontWeight: 800, fontSize: '12px',
                                  cursor: outcomeMarked ? 'not-allowed' : 'pointer',
                                  opacity: outcomeMarked && outcomeMarked !== 'churned' ? 0.4 : 1
                                }}
                              >
                                ❌ Mark as Churned
                              </button>
                            </div>
                            {outcomeMarked && (
                              <div style={{
                                marginTop: '10px', padding: '10px 16px',
                                background: outcomeMarked === 'renewed' ? '#f0fdf4' : '#fef2f2',
                                border: `1px solid ${outcomeMarked === 'renewed' ? '#bbf7d0' : '#fecaca'}`,
                                borderRadius: '12px', textAlign: 'center'
                              }}>
                                <p style={{ fontSize: '12px', fontWeight: 700, color: outcomeMarked === 'renewed' ? '#16a34a' : '#dc2626' }}>
                                  {outcomeMarked === 'renewed'
                                    ? '🎉 Marked as Renewed. Success case saved to ChromaDB.'
                                    : '⚠️ Marked as Churned. Rule weights adjusted. Flagged for Admin.'}
                                </p>
                              </div>
                            )}
                          </div>
                        )}
                        {approveStatus === 'error' && (
                          <p className="text-xs text-rose-600 font-bold text-center mt-2">
                            Something went wrong. Please try again.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {selectedAccount && (
                  <div className="bg-white border border-slate-200 rounded-[32px] p-8 shadow-sm col-span-full mt-8">
                    <div className="flex justify-between items-center mb-6">
                      <h3 className="text-base font-black uppercase text-slate-500 flex items-center gap-2 tracking-widest">
                        <span className="w-1.5 h-6 bg-indigo-500 rounded-full"></span>
                        Similar Past Accounts
                      </h3>
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                        Historical churn cases with similar risk signals — from IBM Telco Dataset
                      </span>
                    </div>

                    {loadingSimilar && (
                      <div className="p-8 text-center text-slate-400 font-bold">Loading similar cases...</div>
                    )}

                    {!loadingSimilar && similarCases.length === 0 && (
                      <div className="p-8 text-center text-slate-400 font-bold">No similar cases found.</div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      {!loadingSimilar && similarCases.map((c, i) => (
                        <div key={i} style={{
                          background: '#f8fafc', border: '1px solid #e2e8f0',
                          borderRadius: '16px', padding: '14px', marginBottom: '10px'
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                            <span style={{ fontSize: '11px', fontWeight: 800, color: '#6366f1' }}>Case {i + 1}</span>
                            {c.similarity_score && (
                              <span style={{ fontSize: '11px', fontWeight: 800, color: '#16a34a', background: '#f0fdf4', padding: '2px 8px', borderRadius: '6px' }}>
                                {Math.round(c.similarity_score * 100)}% match
                              </span>
                            )}
                          </div>
                          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '8px' }}>
                            <span style={{ fontSize: '10px', fontWeight: 700, background: '#eef2ff', color: '#6366f1', padding: '2px 8px', borderRadius: '6px' }}>{c.contract}</span>
                            <span style={{ fontSize: '10px', fontWeight: 700, background: '#f1f5f9', color: '#475569', padding: '2px 8px', borderRadius: '6px' }}>{c.tenure}m tenure</span>
                            <span style={{ fontSize: '10px', fontWeight: 700, background: '#f1f5f9', color: '#475569', padding: '2px 8px', borderRadius: '6px' }}>${c.monthly_charges}/mo</span>
                          </div>
                          {c.churn_reason && c.churn_reason !== 'Not specified' && (
                            <p style={{ fontSize: '11px', color: '#dc2626', fontWeight: 700, marginBottom: '6px' }}>
                              ⚠️ {c.churn_reason}
                            </p>
                          )}
                          {(c.what_worked || c.action) && (
                            <p style={{ fontSize: '11px', color: '#16a34a', fontWeight: 600, lineHeight: '1.4' }}>
                              💡 {c.what_worked || c.action}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-20 bg-white border border-slate-100 rounded-[48px] shadow-sm">
                <div className="w-32 h-32 bg-slate-50 rounded-[40px] flex items-center justify-center mb-8 shadow-inner group transition-all">
                  <span className="text-5xl group-hover:rotate-12 transition-transform duration-500">🔍</span>
                </div>
                <h3 className="text-2xl font-black text-slate-800 mb-3 tracking-tight">Select an Account</h3>
                <p className="text-slate-400 text-sm max-w-[320px] leading-relaxed">Choose a customer profile from the left sidebar to inspect their behavioral health and trigger AI retention workflows.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      <Chatbot selectedAccountId={selectedAccountId} />

      {/* Modals */}
      {showAddModal && (
        <Modal title="Add New Portfolio" onClose={() => setShowAddModal(false)}>
          <form onSubmit={handleAddAccount} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest">Account ID</label>
                <input required type="text" placeholder="ACC-001" className="w-full p-4 bg-slate-50 border border-slate-100 rounded-2xl outline-none focus:ring-2 focus:ring-indigo-100"
                  value={newAcc.id} onChange={e => setNewAcc({ ...newAcc, id: e.target.value })} />
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest">Client Name</label>
                <input required type="text" placeholder="Acme Corp" className="w-full p-4 bg-slate-50 border border-slate-100 rounded-2xl outline-none focus:ring-2 focus:ring-indigo-100"
                  value={newAcc.name} onChange={e => setNewAcc({ ...newAcc, name: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest">Monthly Charges ($)</label>
                <input required type="number" placeholder="1200" className="w-full p-4 bg-slate-50 border border-slate-100 rounded-2xl outline-none focus:ring-2 focus:ring-indigo-100"
                  value={newAcc.monthly_charges} onChange={e => setNewAcc({ ...newAcc, monthly_charges: e.target.value })} />
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest">Tenure (Months)</label>
                <input required type="number" placeholder="12" className="w-full p-4 bg-slate-50 border border-slate-100 rounded-2xl outline-none focus:ring-2 focus:ring-indigo-100"
                  value={newAcc.tenure} onChange={e => setNewAcc({ ...newAcc, tenure: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest">Contract Type</label>
                <select className="w-full p-4 bg-slate-50 border border-slate-100 rounded-2xl outline-none focus:ring-2 focus:ring-indigo-100"
                  value={newAcc.contract_type} onChange={e => setNewAcc({ ...newAcc, contract_type: e.target.value })}>
                  <option>Monthly</option>
                  <option>Annual</option>
                  <option>2-Year</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest">Contract Value ($)</label>
                <input readOnly type="number" placeholder="Calculated" className="w-full p-4 bg-indigo-50/50 border border-indigo-100 rounded-2xl outline-none text-indigo-600 font-bold"
                  value={newAcc.contract_value} />
                <p className="text-[9px] text-slate-400 font-medium italic mt-1">* Auto-calculated (Monthly × Tenure)</p>
              </div>
            </div>
            <button type="submit" className="w-full py-4 mt-4 bg-indigo-600 text-white rounded-2xl font-black shadow-lg shadow-indigo-100 hover:bg-indigo-700 transition-all">
              Initialize Portfolio
            </button>
          </form>
        </Modal>
      )}

      {showProfile && (
        <Modal title="User Profile" onClose={() => { setShowProfile(false); setIsEditingProfile(false); }}>
          <div className="space-y-6">
            <div className="flex items-center gap-6 p-6 bg-slate-50 rounded-[32px] border border-slate-100">
              <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-indigo-500 to-purple-600 p-1 shadow-lg shadow-indigo-100">
                <img src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${userName}`} alt="Avatar" className="w-full h-full rounded-[22px] bg-white" />
              </div>
              <div className="flex-1">
                {isEditingProfile ? (
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full px-4 py-2 bg-white border border-indigo-200 rounded-xl font-bold text-slate-900 outline-none ring-2 ring-indigo-50"
                    placeholder="Enter your name"
                  />
                ) : (
                  <h4 className="text-xl font-black text-slate-900">{userName}</h4>
                )}
                <p className="text-sm font-bold text-indigo-600 mt-1">Senior Customer Success Manager</p>
                <div className="mt-2 flex gap-2">
                  <span className="px-2 py-0.5 bg-emerald-50 text-emerald-600 text-[10px] font-black rounded-lg border border-emerald-100 uppercase">Active</span>
                  <span className="px-2 py-0.5 bg-indigo-50 text-indigo-600 text-[10px] font-black rounded-lg border border-indigo-100 uppercase">Admin</span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="p-5 bg-white border border-slate-100 rounded-3xl">
                <p className="text-[10px] text-slate-400 font-black uppercase tracking-widest mb-1">Email</p>
                <p className="text-sm font-bold text-slate-700 truncate">{localStorage.getItem('user_email') || 'alex@churnalert.ai'}</p>
              </div>
              <div className="p-5 bg-white border border-slate-100 rounded-3xl">
                <p className="text-[10px] text-slate-400 font-black uppercase tracking-widest mb-1">Portfolio Value</p>
                <p className="text-sm font-bold text-slate-700">$2.4M ARR</p>
              </div>
            </div>

            {isEditingProfile ? (
              <div className="flex gap-3">
                <button
                  onClick={() => setIsEditingProfile(false)}
                  className="flex-1 py-4 bg-slate-100 text-slate-600 rounded-2xl font-black hover:bg-slate-200 transition-all"
                >
                  Cancel
                </button>
                <button
                  onClick={handleUpdateProfile}
                  className="flex-[2] py-4 bg-indigo-600 text-white rounded-2xl font-black shadow-lg shadow-indigo-100 hover:bg-indigo-700 transition-all"
                >
                  Save Changes
                </button>
              </div>
            ) : (
              <button
                onClick={() => { setIsEditingProfile(true); setEditName(userName); }}
                className="w-full py-4 bg-indigo-600 text-white rounded-2xl font-black shadow-lg shadow-indigo-100 hover:bg-indigo-700 transition-all"
              >
                Update Profile
              </button>
            )}
          </div>
        </Modal>
      )}

      {showSettings && (
        <Modal title="System Settings" onClose={() => setShowSettings(false)}>
          <div className="space-y-4">
            {systemSettings.map((s) => (
              <button
                key={s.id}
                onClick={() => toggleSetting(s.id)}
                className="w-full flex items-center justify-between p-5 bg-white border border-slate-100 rounded-3xl hover:border-indigo-200 transition-all group text-left"
              >
                <div className="max-w-[70%]">
                  <p className="text-sm font-black text-slate-800 mb-1">{s.label}</p>
                  <p className="text-xs text-slate-400 font-medium leading-tight">{s.desc}</p>
                </div>
                <div className={`w-12 h-6 rounded-full p-1 transition-colors pointer-events-none ${s.active ? 'bg-indigo-600' : 'bg-slate-200'}`}>
                  <motion.div
                    initial={false}
                    animate={{ x: s.active ? 24 : 0 }}
                    className="w-4 h-4 bg-white rounded-full shadow-sm"
                  ></motion.div>
                </div>
              </button>
            ))}

            <button
              onClick={handleSaveSettings}
              disabled={isSavingSettings}
              className="w-full py-4 mt-4 bg-slate-900 text-white rounded-2xl font-black shadow-lg shadow-slate-100 hover:bg-slate-800 transition-all flex items-center justify-center gap-3 disabled:opacity-70"
            >
              {isSavingSettings ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              ) : 'Save Global Configuration'}
            </button>
          </div>
        </Modal>
      )}

      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
      `}</style>
    </div>
  )
}

function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        onClick={onClose}
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
      ></motion.div>
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="relative w-full max-w-lg bg-white rounded-[48px] shadow-2xl border border-white p-10 overflow-hidden"
      >
        <div className="flex justify-between items-center mb-10">
          <h3 className="text-2xl font-black tracking-tight text-slate-900">{title}</h3>
          <button onClick={onClose} className="w-10 h-10 flex items-center justify-center bg-slate-50 text-slate-400 hover:text-slate-900 rounded-xl transition-all font-black text-xl">×</button>
        </div>
        {children}
      </motion.div>
    </div>
  );
}

function TicketItem({ ticket }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const getSentimentIcon = (s) => {
    if (s === 'negative') return '💢';
    if (s === 'positive') return '🌟';
    return '⚖️';
  };

  return (
    <div
      onClick={() => setIsExpanded(!isExpanded)}
      className={`flex flex-col p-4 bg-white rounded-2xl border transition-all cursor-pointer ${isExpanded ? 'border-indigo-400 shadow-md ring-4 ring-indigo-50' : 'border-slate-100 hover:border-slate-300'
        }`}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 overflow-hidden">
          <span className="text-xl flex-shrink-0">{getSentimentIcon(ticket.sentiment)}</span>
          <span className={`text-slate-700 font-bold text-sm ${isExpanded ? 'break-words' : 'truncate'}`}>
            {ticket.subject}
          </span>
        </div>
        <span className={`flex-shrink-0 px-3 py-1 rounded-full font-black uppercase text-[10px] tracking-tighter border ${ticket.sentiment === 'negative' ? 'bg-rose-50 text-rose-600 border-rose-100' :
          ticket.sentiment === 'positive' ? 'bg-emerald-50 text-emerald-600 border-emerald-100' :
            'bg-slate-50 text-slate-500 border-slate-200'
          }`}>
          {ticket.sentiment}
        </span>
      </div>

      {isExpanded && (
        <div className="mt-4 pt-4 border-t border-slate-100 text-xs text-slate-500 leading-relaxed animate-in fade-in slide-in-from-top-2">
          <p className="mb-2 font-black text-slate-400 uppercase tracking-widest text-[9px]">Expanded Transcript</p>
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 italic text-slate-600">
            "{ticket.subject} - full resolution details pending. Ticket was created with {ticket.sentiment} sentiment and is currently {ticket.is_resolved ? 'closed' : 'open'}."
          </div>
          <div className="mt-3 flex justify-between items-center text-[10px]">
            <span className="text-indigo-600 font-bold tracking-tighter uppercase bg-indigo-50 px-2 py-0.5 rounded">ID: TKT-{Math.random().toString(16).slice(2, 6).toUpperCase()}</span>
            <span className="text-slate-400">Logged: {new Date(ticket.created_at).toLocaleDateString()}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard
