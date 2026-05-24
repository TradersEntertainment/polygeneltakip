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

  const handleRemove = async (addressToRemove: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/whales/${addressToRemove}`, { method: 'DELETE' });
      if (response.ok) {
        showToast('Balina takipten çıkarıldı.');
        fetchWhales();
      }
    } catch (e) {
      showToast('Hata oluştu!');
    }
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

  // Calculate total stats
  const totalUSDC = Object.values(balances).reduce((sum, b) => sum + (b.usdc_balance || 0), 0);
  const totalPortfolio = Object.values(balances).reduce((sum, b) => sum + (b.portfolio_value || 0), 0);
  const lowBalanceCount = Object.values(balances).filter(b => b.usdc_balance < 1000).length;

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
            <span className="stat-value">{whales.length} 🐋</span>
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
          <h2 style={{ marginBottom: '25px', color: 'var(--accent-purple)' }}>Takip Edilen Balinalar ({whales.length})</h2>
          
          {whales.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🐋</div>
              <h3>Henüz takip edilen balina yok</h3>
              <p>Sol taraftaki formu kullanarak ilk balinanızı ekleyin.</p>
            </div>
          ) : (() => {
            // Group whales by chat_id
            const groups: Record<string, Whale[]> = {};
            const ungrouped: Whale[] = [];
            
            whales.forEach((whale) => {
              if (whale.chat_id) {
                if (!groups[whale.chat_id]) groups[whale.chat_id] = [];
                groups[whale.chat_id].push(whale);
              } else {
                ungrouped.push(whale);
              }
            });

            const chatIds = Object.keys(groups);

            const renderWhaleCard = (whale: Whale) => {
              const bal = balances[whale.address.toLowerCase()] || balances[whale.address];
              const hasBalance = bal !== undefined;
              const usdcBalance = bal?.usdc_balance ?? 0;
              const portfolioValue = bal?.portfolio_value ?? 0;

              return (
                <div key={whale.id} className={`whale-card ${hasBalance && usdcBalance < 1000 ? 'whale-card-alert' : ''}`}>
                  <div className="whale-info">
                    <h3>
                      <span className="status-indicator" title="Aktif olarak takip ediliyor"></span>
                      {whale.name}
                    </h3>
                    <p>{whale.address}</p>
                    
                    {hasBalance ? (
                      <div className="balance-row">
                        <span className={`balance-badge ${getBalanceClass(usdcBalance)}`}>
                          💰 {formatBalance(usdcBalance)} USDC
                        </span>
                        <span className="balance-badge balance-portfolio">
                          📊 {formatBalance(portfolioValue)} Portfolio
                        </span>
                      </div>
                    ) : (
                      <div className="balance-row">
                        <span className="balance-badge balance-loading">
                          ⏳ Bakiye yükleniyor...
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="whale-actions">
                    <button 
                      onClick={() => handleRemove(whale.address)}
                      className="btn btn-danger"
                      style={{ padding: '8px 15px', fontSize: '0.9rem' }}
                    >
                      Sil
                    </button>
                  </div>
                </div>
              );
            };

            return (
              <div>
                {/* Grouped whales by chat_id */}
                {chatIds.map((chatId, groupIndex) => (
                  <div key={chatId} className={`chat-group color-${groupIndex % 7}`}>
                    <div className="chat-group-header">
                      <div className="chat-group-dot"></div>
                      <span className="chat-group-label">📱 {chatId}</span>
                      <span className="chat-group-count">{groups[chatId].length} balina</span>
                    </div>
                    <div className="whale-list">
                      {groups[chatId].map(renderWhaleCard)}
                    </div>
                  </div>
                ))}

                {/* Ungrouped whales (no chat_id) */}
                {ungrouped.length > 0 && (
                  <div className="chat-group color-ungrouped">
                    <div className="chat-group-header">
                      <div className="chat-group-dot"></div>
                      <span className="chat-group-label">Gruplanmamış (Varsayılan Chat)</span>
                      <span className="chat-group-count">{ungrouped.length} balina</span>
                    </div>
                    <div className="whale-list">
                      {ungrouped.map(renderWhaleCard)}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      </div>

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
