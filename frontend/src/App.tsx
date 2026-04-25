import React, { useState, useEffect } from 'react';
import './index.css';

interface Whale {
  id: string;
  address: string;
  name: string;
  addedAt: string;
  status: 'tracking' | 'paused';
}

function App() {
  const [whales, setWhales] = useState<Whale[]>([]);
  const [address, setAddress] = useState('');
  const [name, setName] = useState('');
  const [toast, setToast] = useState<{ message: string; visible: boolean }>({ message: '', visible: false });

  // Load from API
  const fetchWhales = async () => {
    try {
      const response = await fetch('/api/whales');
      const data = await response.json();
      setWhales(data.whales);
    } catch (e) {
      console.error('Error fetching whales', e);
    }
  };

  useEffect(() => {
    fetchWhales();
    // Optional: poll every 10 seconds for updates
    const interval = setInterval(fetchWhales, 10000);
    return () => clearInterval(interval);
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
      const response = await fetch('/api/whales', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address, name })
      });
      
      if (response.ok) {
        setAddress('');
        setName('');
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
      const response = await fetch(`/api/whales/${addressToRemove}`, { method: 'DELETE' });
      if (response.ok) {
        showToast('Balina takipten çıkarıldı.');
        fetchWhales();
      }
    } catch (e) {
      showToast('Hata oluştu!');
    }
  };

  return (
    <div className="container">
      <header className="header">
        <h1 className="gradient-text">Poly Whale Tracker</h1>
        <p>Polymarket'teki balinaların cüzdan hareketlerini canlı takip edin</p>
      </header>

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
          ) : (
            <div className="whale-list">
              {whales.map((whale) => (
                <div key={whale.id} className="whale-card">
                  <div className="whale-info">
                    <h3>
                      <span className="status-indicator" title="Aktif olarak takip ediliyor"></span>
                      {whale.name}
                    </h3>
                    <p>{whale.address}</p>
                    <div style={{ fontSize: '0.75rem', marginTop: '5px', color: 'rgba(255,255,255,0.4)' }}>
                      Eklendi: {whale.addedAt}
                    </div>
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
              ))}
            </div>
          )}
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
