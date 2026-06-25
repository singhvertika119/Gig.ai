"use client";

import React, { useState, useEffect } from "react";

// Zero-dependency lightweight markdown-to-html parser
function renderMarkdown(md: string): string {
  if (!md) return "";
  let html = md.replace(/\r\n/g, "\n");
  
  // Headers
  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");
  
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  
  // Bullet Lists
  html = html.replace(/^\* (.*$)/gim, "<li>$1</li>");
  html = html.replace(/^- (.*$)/gim, "<li>$1</li>");
  
  // Paragraphs and Tables
  const blocks = html.split("\n\n");
  const processed = blocks.map(block => {
    const trimmed = block.trim();
    if (!trimmed) return "";
    
    // Check if block is a markdown table
    if (trimmed.startsWith("|")) {
      return parseMarkdownTable(trimmed);
    }
    
    // Skip wrapping custom HTML elements in paragraph tags
    if (
      trimmed.startsWith("<h") || 
      trimmed.startsWith("<table") || 
      trimmed.startsWith("<tr") || 
      trimmed.startsWith("<li>")
    ) {
      return trimmed;
    }
    
    return `<p>${trimmed.replace(/\n/g, "<br/>")}</p>`;
  });
  
  return processed.join("\n");
}

function parseMarkdownTable(block: string): string {
  const lines = block.split("\n").map(l => l.trim()).filter(l => l.startsWith("|"));
  if (lines.length < 2) return "";
  
  let html = "<table>";
  lines.forEach((line, index) => {
    const cols = line.split("|").map(c => c.trim()).slice(1, -1);
    
    // Skip separator lines e.g. |---|---|
    if (cols.every(c => /^:?-+:?$/.test(c))) {
      return;
    }
    
    html += "<tr>";
    cols.forEach(col => {
      const tag = index === 0 ? "th" : "td";
      html += `<${tag}>${col}</${tag}>`;
    });
    html += "</tr>";
  });
  
  html += "</table>";
  return html;
}

export default function Dashboard() {
  const [brief, setBrief] = useState("");
  const [activeTab, setActiveTab] = useState<"projects" | "invoices">("projects");
  
  // Data lists
  const [projects, setProjects] = useState<any[]>([]);
  const [invoices, setInvoices] = useState<any[]>([]);
  
  // UI Loading States
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [loadingInvoices, setLoadingInvoices] = useState(false);
  const [submittingProposal, setSubmittingProposal] = useState(false);
  const [markingOverdueId, setMarkingOverdueId] = useState<number | null>(null);
  
  // Results
  const [generatedProposal, setGeneratedProposal] = useState<any | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  
  // Chat Assistant State
  const [chatQuery, setChatQuery] = useState("");
  const [chatMessages, setChatMessages] = useState<Array<{ sender: "user" | "bot"; text: string; sql?: string | null }>>([
    { sender: "bot", text: "Hello! I am your database assistant. Ask me anything about our clients, projects, milestones, or invoices!" }
  ]);
  const [chatLoading, setChatLoading] = useState(false);
  
  // API URL
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Handle Send Chat
  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatQuery.trim() || chatLoading) return;

    const userMsg = chatQuery.trim();
    setChatQuery("");
    setChatMessages((prev) => [...prev, { sender: "user", text: userMsg }]);
    setChatLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to query database.");
      }
      setChatMessages((prev) => [
        ...prev,
        { sender: "bot", text: data.answer, sql: data.generated_sql }
      ]);
    } catch (err: any) {
      setChatMessages((prev) => [
        ...prev,
        { sender: "bot", text: `⚠️ Error: ${err.message}` }
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  // Fetch Database tables
  const fetchProjects = async () => {
    setLoadingProjects(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/projects`, { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to fetch projects");
      const data = await res.json();
      setProjects(data);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoadingProjects(false);
    }
  };

  const fetchInvoices = async () => {
    setLoadingInvoices(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/invoices`, { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to fetch invoices");
      const data = await res.json();
      setInvoices(data);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoadingInvoices(false);
    }
  };

  useEffect(() => {
    fetchProjects();
    fetchInvoices();
  }, []);

  // Auto-scroll chat window to bottom
  useEffect(() => {
    const chatContainer = document.getElementById("chat-messages");
    if (chatContainer) {
      chatContainer.scrollTop = chatContainer.scrollHeight;
    }
  }, [chatMessages, chatLoading]);

  // Submit client brief to LangGraph
  const handleSubmitProposal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!brief.trim()) return;
    
    setSubmittingProposal(true);
    setApiError(null);
    setGeneratedProposal(null);
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/proposals/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brief }),
      });
      
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Proposal generation failed.");
      }
      
      setGeneratedProposal(data);
      setBrief(""); // Clear brief input
      // Reload projects and invoices tables
      fetchProjects();
      fetchInvoices();
    } catch (err: any) {
      setApiError(err.message || "Something went wrong.");
    } finally {
      setSubmittingProposal(false);
    }
  };

  // Mark an invoice overdue & trigger n8n notification webhook
  const handleMarkOverdue = async (invoiceId: number) => {
    setMarkingOverdueId(invoiceId);
    try {
      const res = await fetch(`${API_BASE_URL}/api/invoices/${invoiceId}/mark-overdue`, {
        method: "POST",
      });
      const data = await res.json();
      
      if (!res.ok) throw new Error(data.detail || "Failed to update invoice.");
      
      // Notify outcome
      alert(
        `Invoice #${invoiceId} status updated to OVERDUE in SQL database.\n\n` + 
        `The Ops Agent background workflow has been triggered asynchronously. It will query relationships and dispatch reminder notifications via n8n webhook, direct email, or Discord as configured.`
      );
      
      // Reload invoices
      fetchInvoices();
    } catch (err: any) {
      alert(`Error: ${err.message}`);
    } finally {
      setMarkingOverdueId(null);
    }
  };

  return (
    <div className="app-container">
      {/* Page Header */}
      <header className="app-header">
        <div className="logo-group">
          <span className="logo-badge">Gig.ai</span>
          <span className="logo-text">Operations Console</span>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button className="tab-btn" onClick={() => { fetchProjects(); fetchInvoices(); }} style={{ fontSize: "0.85rem", border: "1px solid var(--card-border)" }}>
            🔄 Refresh Dashboard
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <div className="dashboard-grid">
        
        {/* Left Side: Scoping Input & Proposal Renderer */}
        <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
          
          {/* Card: Database AI Assistant */}
          <div className="dash-card">
            <h2 className="card-title">💬 Database AI Assistant</h2>
            <div className="chat-container">
              <div className="chat-messages" id="chat-messages">
                {chatMessages.map((msg, i) => (
                  <div key={i} className={`chat-bubble-wrapper ${msg.sender}`}>
                    <div className={`chat-bubble ${msg.sender}`}>
                      <p>{msg.text}</p>
                      {msg.sql && (
                        <details className="chat-sql-details">
                          <summary>🔍 View Generated SQL</summary>
                          <code>{msg.sql}</code>
                        </details>
                      )}
                    </div>
                  </div>
                ))}
                {chatLoading && (
                  <div className="chat-bubble-wrapper bot">
                    <div className="chat-bubble bot loading" style={{ display: "flex", gap: "0.25rem", alignItems: "center" }}>
                      <span className="typing-dot"></span>
                      <span className="typing-dot"></span>
                      <span className="typing-dot"></span>
                    </div>
                  </div>
                )}
              </div>
              <form onSubmit={handleSendChat} className="chat-input-form">
                <input
                  id="chat-input"
                  type="text"
                  className="chat-input"
                  placeholder="Ask a question about database..."
                  value={chatQuery}
                  onChange={(e) => setChatQuery(e.target.value)}
                  disabled={chatLoading}
                  required
                />
                <button
                  id="chat-submit-btn"
                  type="submit"
                  className="btn-primary"
                  disabled={chatLoading || !chatQuery.trim()}
                  style={{ width: "auto", padding: "0 1.5rem" }}
                >
                  Ask
                </button>
              </form>
            </div>
          </div>

          <div className="dash-card">
            <h2 className="card-title">📝 Proposal Scoping Agent</h2>
            <form onSubmit={handleSubmitProposal} className="form-group">
              <label htmlFor="brief" className="form-label">
                Paste Messy Client Brief
              </label>
              <textarea
                id="brief"
                className="form-textarea"
                placeholder="E.g., We need a mobile portal for Orion Ventures. Budget is $30,000. Start next week. We need mockups in 10 days for $10,000, development in 30 days for $20,000. Contact: info@orion.com"
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                required
                disabled={submittingProposal}
              />
              <button 
                id="submit-brief-btn"
                type="submit" 
                className="btn-primary" 
                disabled={submittingProposal || !brief.trim()}
                style={{ marginTop: "0.5rem" }}
              >
                {submittingProposal ? (
                  <>
                    <span className="spinner"></span> Running Multi-Agent Scoping...
                  </>
                ) : (
                  "Generate Project & Proposal"
                )}
              </button>
            </form>
            {apiError && (
              <div style={{ color: "var(--status-overdue-fg)", fontSize: "0.9rem", background: "rgba(239,68,68,0.1)", padding: "1rem", borderRadius: "0.5rem", border: "1px solid rgba(239,68,68,0.2)" }}>
                ⚠️ <strong>Error:</strong> {apiError}
              </div>
            )}
          </div>

          {/* Show Generated proposal preview */}
          {generatedProposal && (
            <div className="dash-card" style={{ border: "1px solid var(--accent)" }}>
              <h2 className="card-title" style={{ color: "var(--accent)" }}>✨ Generated Proposal Draft</h2>
              
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", background: "rgba(255,255,255,0.02)", padding: "1rem", borderRadius: "0.5rem", fontSize: "0.85rem", border: "1px solid var(--card-border)" }}>
                <div>
                  <span style={{ color: "var(--muted)" }}>Project Name:</span>
                  <p style={{ fontWeight: 600, color: "#fff", textAlign: "left" }}>{generatedProposal.project_scope?.project_name}</p>
                </div>
                <div>
                  <span style={{ color: "var(--muted)" }}>Client Name:</span>
                  <p style={{ fontWeight: 600, color: "#fff", textAlign: "left" }}>{generatedProposal.project_scope?.client_name || "Valued Client"}</p>
                </div>
                <div>
                  <span style={{ color: "var(--muted)" }}>Total Budget:</span>
                  <p style={{ fontWeight: 600, color: "#fff", textAlign: "left" }}>${generatedProposal.project_scope?.budget?.toLocaleString()}</p>
                </div>
                <div>
                  <span style={{ color: "var(--muted)" }}>Client Email:</span>
                  <p style={{ fontWeight: 600, color: "#fff", textAlign: "left" }}>{generatedProposal.project_scope?.client_email || "N/A"}</p>
                </div>
              </div>

              <div className="proposal-render" dangerouslySetInnerHTML={{ __html: renderMarkdown(generatedProposal.proposal_draft) }} />
            </div>
          )}
        </div>

        {/* Right Side: Databases (Projects & Invoices) */}
        <div className="dash-card">
          <div className="tabs-nav">
            <button 
              id="projects-tab-btn"
              className={`tab-btn ${activeTab === "projects" ? "active" : ""}`}
              onClick={() => setActiveTab("projects")}
            >
              📂 Active Projects ({projects.length})
            </button>
            <button 
              id="invoices-tab-btn"
              className={`tab-btn ${activeTab === "invoices" ? "active" : ""}`}
              onClick={() => setActiveTab("invoices")}
            >
              💳 Invoices ({invoices.length})
            </button>
          </div>

          {/* Projects Table */}
          {activeTab === "projects" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {loadingProjects ? (
                <div className="empty-state">
                  <span className="spinner" style={{ width: "2rem", height: "2rem" }}></span>
                  <p>Loading projects...</p>
                </div>
              ) : projects.length === 0 ? (
                <div className="empty-state">
                  📂 No projects currently tracked. Submit a brief on the left to start.
                </div>
              ) : (
                <div className="table-container">
                  <table className="dash-table">
                    <thead>
                      <tr>
                        <th>Project Name</th>
                        <th>Client</th>
                        <th>Budget</th>
                        <th>Status</th>
                        <th>Deadline</th>
                      </tr>
                    </thead>
                    <tbody>
                      {projects.map((proj) => (
                        <tr key={proj.id}>
                          <td style={{ fontWeight: 600 }}>{proj.name}</td>
                          <td>{proj.client_name || "Valued Client"}</td>
                          <td style={{ color: "#fff", fontWeight: 500 }}>
                            {proj.budget ? `$${proj.budget.toLocaleString()}` : "N/A"}
                          </td>
                          <td>
                            <span className={`status-badge ${proj.status}`}>
                              {proj.status}
                            </span>
                          </td>
                          <td style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                            {proj.end_date || "N/A"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Invoices Table */}
          {activeTab === "invoices" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {loadingInvoices ? (
                <div className="empty-state">
                  <span className="spinner" style={{ width: "2rem", height: "2rem" }}></span>
                  <p>Loading invoices...</p>
                </div>
              ) : invoices.length === 0 ? (
                <div className="empty-state">
                  💳 No invoices currently tracked.
                </div>
              ) : (
                <div className="table-container">
                  <table className="dash-table">
                    <thead>
                      <tr>
                        <th>Invoice ID</th>
                        <th>Project / Client</th>
                        <th>Amount</th>
                        <th>Client Email</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invoices.map((inv) => (
                        <tr key={inv.id}>
                          <td style={{ fontWeight: 600 }}>#{inv.id}</td>
                          <td>
                            <div style={{ fontWeight: 500 }}>{inv.project_name}</div>
                            <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>{inv.client_name || "Valued Client"}</div>
                          </td>
                          <td style={{ color: "#fff", fontWeight: 600 }}>${inv.amount?.toLocaleString()}</td>
                          <td style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{inv.client_email || "billing@example.com"}</td>
                          <td>
                            <span className={`status-badge ${inv.status}`}>
                              {inv.status}
                            </span>
                          </td>
                          <td>
                            {inv.status !== "overdue" && inv.status !== "paid" ? (
                              <button
                                className="btn-action-small"
                                onClick={() => handleMarkOverdue(inv.id)}
                                disabled={markingOverdueId === inv.id}
                              >
                                {markingOverdueId === inv.id ? (
                                  "Marking..."
                                ) : (
                                  "⚠️ Mark Overdue"
                                )}
                              </button>
                            ) : (
                              <span style={{ fontSize: "0.8rem", color: "var(--muted)" }}>—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
