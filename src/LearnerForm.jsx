import React, { useState } from 'react';

export default function LearnerForm({ onSubmit }) {
  const [learnerId, setLearnerId] = useState('U_1026161');
  const [targetConceptId, setTargetConceptId] = useState('Pm_738116');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!learnerId || !targetConceptId) {
      alert("Vui long nhap day du Learner ID va Target Concept ID!");
      return;
    }
    onSubmit({ learnerId, targetConceptId });
  };

  return (
    <div style={{ padding: '20px', border: '1px solid #ccc', borderRadius: '8px', maxWidth: '400px' }}>
      <h2>Lua chon Lo trinh Hoc tap</h2>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px' }}>Ma Nguoi Hoc (Learner ID):</label>
          <input 
            type="text" 
            value={learnerId} 
            onChange={(e) => setLearnerId(e.target.value)}
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px' }}>Muc tieu (Target Concept ID):</label>
          <input 
            type="text" 
            value={targetConceptId} 
            onChange={(e) => setTargetConceptId(e.target.value)}
            style={{ width: '100%', padding: '8px' }}
          />
        </div>

        <button type="submit" style={{ padding: '10px 16px', backgroundColor: '#007bff', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
          Tao Lo Trinh (Call API)
        </button>
      </form>
    </div>
  );
}
