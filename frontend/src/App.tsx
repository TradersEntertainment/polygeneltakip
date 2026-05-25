import React, { useState, useEffect } from 'react';
import './index.css';

interface Whale {
  id: string;
  address: string;
  name: string;
  addedAt: string;
  status: 'tracking' | 'paused';
  chat_id?: string;
}

interface BalanceInfo {
  usdc_balance: number;
  portfolio_value: number;
  last_updated: number;
  nickname: string;
}

function App() {
  const [whales, setWhales] = useState<Whale[]>([]);
  const [balances, setBalances] = useState<Record<string, BalanceInfo>>({});
  const [address, setAddress] = useState('');
  const [name, setName] = useState('');
  const [chatId, setChatId] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [toast, setToast] = useState<{ message: string; visible: boolean }>({ message: '', visible: false });

  const API_BASE = import.meta.env.VITE_API_URL || '';

  // Load whales from API
  const fetchWhales = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/whales`);
      const data = await response.json();
      setWhales(data.whales);
    } catch (e) {
      console.error('Error fetching whales', e);
    }
  };

  // Load balances from API
  const fetchBalances = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/balances`);
      const data = await response.json();
      setBalances(data.balances || {});
    } catch (e) {
      console.error('Error fetching balances', e);
    }
  };

  useEffect(() => {
    fetchWhales();
    fetchBalances();
    // Poll whales every 10s, balances every 30s
    const whaleInterval = setInterval(fetchWhales, 10000);
    const balanceInterval = setInterval(fetchBalances, 30000);
    return () => {
      clearInterval(whaleInterval);
      clearInterval(balanceInterval);
    };
  }, []);

  const showToast = (message: string) => {
    setToast({ message, visible: true });
    setTimeout(() => setToast({ message: '', visible: false }), 3000);
  };

  const handleAddWhale = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!address || !name) {
      showToast('Lütfen tüm alanları doldurun!');
      return;
    }

    if (!address.startsWith('0x') || address.length !== 42) {
      showToast('Geçerli bir cüzdan adresi girin (0x...)');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/whales`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address, name, chat_id: chatId || null })
      });
      
      if (response.ok) {
        setAddress('');
        setName('');
        setChatId('');
        showToast(`${name} başarıyla eklendi!`);
        fetchWhales();
      } else {
        const error = await response.json();
        showToast(`Hata: ${error.detail || 'Eklenemedi'}`);
      }
    } catch (e) {
      showToast('Bağlantı hatası!');
    }
  };

  const handleRemove = async (addressToRemove: string, name: string) => {
    const confirmed = window.confirm(`"${name}" isimli balinanın takibini durdurmak istediğinize emin misiniz? (Bildirim göndermeyi kesecektir.)`);
    if (!confirmed) return;
    try {
      const response = await fetch(`${API_BASE}/api/whales/${addressToRemove}`, { method: 'DELETE' });
      if (response.ok) {
        showToast('Balina takibi durduruldu. (Silinenler listesine alındı)');
        fetchWhales();
      }
    } catch (e) {
      showToast('Hata oluştu!');
    }
  };

  const handleReactivate = async (addressToReactivate: string, name: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/whales/${addressToReactivate}/reactivate`, { method: 'POST' });
      if (response.ok) {
        showToast(`"${name}" yeniden aktif takibe alındı! 🐋`);
        fetchWhales();
      }
    } catch (e) {
      showToast('Hata oluştu!');
    }
  };

  const handleRemovePermanent = async (addressToRemove: string, name: string) => {
    const confirmed = window.confirm(`"${name}" isimli balinayı veritabanından TAMAMEN silmek istediğinize emin misiniz? Bu işlem geri alınamaz.`);
    if (!confirmed) return;
    try {
      const response = await fetch(`${API_BASE}/api/whales/${addressToRemove}/permanent`, { method: 'DELETE' });
      if (response.ok) {
        showToast('Balina tamamen silindi.');
        fetchWhales();
      }
    } catch (e) {
      showToast('Hata oluştu!');
    }
  };

  const truncateAddress = (addr: string): string => {
    if (!addr) return '';
    return `${addr.substring(0, 6)}...${addr.substring(addr.length - 4)}`;
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    showToast('Cüzdan adresi kopyalandı! 📋');
  };

  const formatBalance = (value: number): string => {
    if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
    return `$${value.toFixed(2)}`;
  };

  const getBalanceClass = (usdc: number): string => {
    if (usdc < 1000) return 'balance-danger';
    if (usdc < 5000) return 'balance-warning';
    return 'balance-ok';
  };

  // Calculate total stats for active whales only
  const activeWhalesList = whales.filter(w => w.status !== 'paused');
  const pausedWhales = whales.filter(w => w.status === 'paused');
  const activeBalances = Object.entries(balances)
    .filter(([addr]) => whales.some(w => w.address.toLowerCase() === addr && w.status !== 'paused'))
    .map(([, b]) => b);

  const totalUSDC = activeBalances.reduce((sum, b) => sum + (b.usdc_balance || 0), 0);
  const totalPortfolio = activeBalances.reduce((sum, b) => sum + (b.portfolio_value || 0), 0);
  const lowBalanceCount = activeBalances.filter(b => b.usdc_balance < 1000).length;

  return (
    <div className="container">
      <header className="header">
        <h1 className="gradient-text">Poly Whale Tracker</h1>
        <p>Polymarket'teki balinaların cüzdan hareketlerini canlı takip edin</p>
      </header>

      {/* Stats Bar */}
      {Object.keys(balances).length > 0 && (
        <div className="stats-bar">
          <div className="stat-item">
            <span className="stat-label">Toplam USDC</span>
            <span className="stat-value cyan">{formatBalance(totalUSDC)}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Toplam Portfolio</span>
            <span className="stat-value purple">{formatBalance(totalPortfolio)}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Takip Edilen</span>
            <span className="stat-value">{activeWhalesList.length} 🐋</span>
          </div>
          {lowBalanceCount > 0 && (
            <div className="stat-item">
              <span className="stat-label">Düşük Bakiye</span>
              <span className="stat-value danger">{lowBalanceCount} ⚠️</span>
            </div>
          )}
        </div>
      )}

      <div className="dashboard-grid">
        {/* Left Column: Add Whale Form */}
        <div className="glass-panel">
          <h2 style={{ marginBottom: '25px', color: 'var(--accent-cyan)' }}>Yeni Balina Ekle</h2>
          
          <form onSubmit={handleAddWhale}>
            <div className="form-group">
              <label htmlFor="name">Balina Adı / Lakabı</label>
              <input
                type="text"
                id="name"
                className="input-field"
                placeholder="Örn: 150dollarsto10k"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="address">Polymarket Cüzdan Adresi</label>
              <input
                type="text"
                id="address"
                className="input-field"
                placeholder="Örn: 0x4fbc41fac6d1cacf16e8eecd4ad6deedbf037a45"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="chatId">Telegram Chat ID (İsteğe Bağlı)</label>
              <input
                type="text"
                id="chatId"
                className="input-field"
                placeholder="Örn: -1001234567890"
                value={chatId}
                onChange={(e) => setChatId(e.target.value)}
              />
            </div>

            <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '10px' }}>
              Takibe Başla
            </button>
          </form>

          <div style={{ marginTop: '40px', fontSize: '0.85rem', color: 'var(--text-secondary)', padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '10px', borderLeft: '3px solid var(--accent-purple)' }}>
            <p><strong>Bilgi:</strong> Eklediğiniz cüzdanın Polymarket üzerindeki işlemleri (TRADE) tespit edildiğinde bağlı Telegram grubuna (-5015496318) anında bildirim gönderilecektir.</p>
          </div>
        </div>

        {/* Right Column: Tracked Whales List */}
        <div className="glass-panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '15px' }}>
            <h2 style={{ margin: 0, color: 'var(--accent-purple)' }}>Takip Edilen Balinalar ({activeWhalesList.length})</h2>
            <div className="search-box">
              <input
                type="text"
                className="search-input"
                placeholder="🔍 Balina adı veya cüzdan adresi ara..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              {searchTerm && (
                <button className="clear-search" onClick={() => setSearchTerm('')}>✕</button>
              )}
            </div>
          </div>
          
          {activeWhalesList.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🐋</div>
              <h3>Henüz aktif takip edilen balina yok</h3>
              <p>Sol taraftaki formu kullanarak ilk balinanızı ekleyin veya aşağıdaki durdurulan balinaları aktifleştirin.</p>
            </div>
          ) : (() => {
            // Group active whales by chat_id or 'ungrouped' after applying search filter
            const filteredActiveWhales = activeWhalesList.filter(w =>
              w.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
              w.address.toLowerCase().includes(searchTerm.toLowerCase())
            );

            if (filteredActiveWhales.length === 0) {
              return (
                <div className="empty-state">
                  <div className="empty-state-icon">🔍</div>
                  <h3>Aramanızla eşleşen aktif balina bulunamadı</h3>
                  <p>Arama terimini kontrol edin veya başka bir anahtar kelime deneyin.</p>
                </div>
              );
            }

            const groupMap: Record<string, Whale[]> = {};
            filteredActiveWhales.forEach((whale) => {
              const cid = whale.chat_id || 'ungrouped';
              if (!groupMap[cid]) groupMap[cid] = [];
              groupMap[cid].push(whale);
            });

            interface GroupData {
              id: string;
              label: string;
              whales: Whale[];
              totalUSDC: number;
              totalPortfolio: number;
              totalValue: number;
            }

            const groupList: GroupData[] = Object.entries(groupMap).map(([cid, groupWhales]) => {
              let totalUSDC = 0;
              let totalPortfolio = 0;
              
              groupWhales.forEach(w => {
                const bal = balances[w.address.toLowerCase()] || balances[w.address];
                if (bal) {
                  totalUSDC += bal.usdc_balance || 0;
                  totalPortfolio += bal.portfolio_value || 0;
                }
              });

              return {
                id: cid,
                label: cid === 'ungrouped' ? 'Gruplanmamış (Varsayılan Chat)' : `📱 ${cid}`,
                whales: groupWhales,
                totalUSDC,
                totalPortfolio,
                totalValue: totalUSDC + totalPortfolio
              };
            });

            // Sort groups by total balance descending (highest first)
            groupList.sort((a, b) => b.totalValue - a.totalValue);

            const renderWhaleCard = (whale: Whale) => {
              const bal = balances[whale.address.toLowerCase()] || balances[whale.address];
              const hasBalance = bal !== undefined;
              const usdcBalance = bal?.usdc_balance ?? 0;
              const portfolioValue = bal?.portfolio_value ?? 0;

              return (
                <div key={whale.id} className={`whale-card ${hasBalance && usdcBalance < 1000 ? 'whale-card-alert' : ''}`}>
                  <div className="whale-card-header">
                    <h3 className="whale-card-title">
                      <span className="status-indicator" title="Aktif olarak takip ediliyor"></span>
                      {whale.name}
                    </h3>
                    <button 
                      onClick={() => handleRemove(whale.address, whale.name)}
                      className="whale-delete-btn"
                      title="Takibi Durdur / Bildirim Kapat"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                      </svg>
                    </button>
                  </div>
                  
                  <div className="whale-card-body">
                    <div className="card-links-row">
                      <span 
                        className="whale-address" 
                        onClick={() => copyToClipboard(whale.address)} 
                        title="Cüzdan Adresini Kopyala"
                      >
                        {truncateAddress(whale.address)} 📋
                      </span>
                      <a 
                        href={`https://www.betmoar.fun/profile/${whale.address}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="betmoar-link"
                        title="Betmoar Profilini İncele"
                      >
                        🔍 Betmoar
                      </a>
                    </div>
                    
                    {hasBalance ? (
                      <div className="balance-row">
                        <span className={`balance-badge ${getBalanceClass(usdcBalance)}`}>
                          💰 {formatBalance(usdcBalance)}
                        </span>
                        <span className="balance-badge balance-portfolio">
                          📊 {formatBalance(portfolioValue)}
                        </span>
                      </div>
                    ) : (
                      <div className="balance-row">
                        <span className="balance-badge balance-loading">
                          ⏳ Yükleniyor...
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            };

            return (
              <div>
                {groupList.map((group, groupIndex) => (
                  <div key={group.id} className={`chat-group color-${group.id === 'ungrouped' ? 'ungrouped' : groupIndex % 7}`}>
                    <div className="chat-group-header">
                      <div className="chat-group-dot"></div>
                      <span className="chat-group-label">{group.label}</span>
                      
                      {(group.totalUSDC > 0 || group.totalPortfolio > 0) && (
                        <div className="chat-group-balance">
                          <span className="group-balance-badge usdc" title="Grup Toplam USDC">
                            💰 {formatBalance(group.totalUSDC)}
                          </span>
                          <span className="group-balance-badge portfolio" title="Grup Toplam Portfolio">
                            📊 {formatBalance(group.totalPortfolio)}
                          </span>
                        </div>
                      )}
                      
                      <span className="chat-group-count">{group.whales.length} balina</span>
                    </div>
                    <div className="whale-grid">
                      {group.whales.map(renderWhaleCard)}
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}
        </div>
      </div>

      {/* Paused/Deleted Whales Section */}
      {(() => {
        const filteredPausedWhales = pausedWhales.filter(w =>
          w.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          w.address.toLowerCase().includes(searchTerm.toLowerCase())
        );

        if (filteredPausedWhales.length === 0) return null;

        return (
          <div className="glass-panel" style={{ marginTop: '30px' }}>
            <h2 style={{ marginBottom: '15px', color: 'var(--text-secondary)' }}>
              🔇 Takibi Durdurulan / Silinen Balinalar ({filteredPausedWhales.length})
            </h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '20px' }}>
              Aşağıdaki cüzdanlar için Telegram bildirimleri <strong>gönderilmez</strong>. Dilediğinizde yeniden takibe alabilir veya kalıcı olarak silebilirsiniz.
            </p>
            
            <div className="whale-grid">
              {filteredPausedWhales.map((whale) => {
                const bal = balances[whale.address.toLowerCase()] || balances[whale.address];
                const hasBalance = bal !== undefined;
                const usdcBalance = bal?.usdc_balance ?? 0;
                const portfolioValue = bal?.portfolio_value ?? 0;

                return (
                  <div key={whale.id} className="whale-card whale-card-paused">
                    <div className="whale-card-header">
                      <h3 className="whale-card-title">
                        <span className="status-indicator status-paused" title="Takip durduruldu"></span>
                        {whale.name}
                      </h3>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <button 
                          onClick={() => handleReactivate(whale.address, whale.name)}
                          className="whale-reactivate-btn"
                          title="Yeniden Aktifleştir"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
                          </svg>
                        </button>
                        <button 
                          onClick={() => handleRemovePermanent(whale.address, whale.name)}
                          className="whale-delete-btn"
                          title="Kalıcı Olarak Veritabanından Sil"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                          </svg>
                        </button>
                      </div>
                    </div>
                    
                    <div className="whale-card-body">
                      <div className="card-links-row">
                        <span 
                          className="whale-address" 
                          onClick={() => copyToClipboard(whale.address)} 
                          title="Cüzdan Adresini Kopyala"
                        >
                          {truncateAddress(whale.address)} 📋
                        </span>
                        <a 
                          href={`https://www.betmoar.fun/profile/${whale.address}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="betmoar-link"
                          title="Betmoar Profilini İncele"
                        >
                          🔍 Betmoar
                        </a>
                      </div>
                      
                      {hasBalance ? (
                        <div className="balance-row">
                          <span className={`balance-badge ${getBalanceClass(usdcBalance)}`}>
                            💰 {formatBalance(usdcBalance)}
                          </span>
                          <span className="balance-badge balance-portfolio">
                            📊 {formatBalance(portfolioValue)}
                          </span>
                        </div>
                      ) : (
                        <div className="balance-row">
                          <span className="balance-badge balance-loading">
                            ⏳ Yükleniyor...
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

      {toast.visible && (
        <div className="toast-container">
          <div className="toast">
            {toast.message}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
