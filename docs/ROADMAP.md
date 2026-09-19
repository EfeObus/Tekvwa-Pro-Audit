# Tekvwa Pro Audit - Project Roadmap

**Document Version:** 1.2  
**Date:** January 27, 2026  
**Planning Horizon:** 18 Months  
**Status:** Phase 2 Complete - SKU Enforcement Live

---

## Vision Statement

> By 2027, Tekvwa Pro Audit will be Nigeria's most trusted tax compliance platform, serving 100,000+ businesses and recognized as an official NRS-certified solution.

---

## Roadmap Overview

```
2026                                                              2027
├─── Q1 ────┼─── Q2 ────┼─── Q3 ────┼─── Q4 ────┼─── Q1 ────┼─── Q2 ────┤
│           │           │           │           │           │           │
│  PHASE 1  │  PHASE 2  │  PHASE 3  │  PHASE 4  │  PHASE 5  │  PHASE 6  │
│  FOUNDATION  MVP      │  GROWTH   │  SCALE    │ ENTERPRISE│ ECOSYSTEM │
│           │  LAUNCH   │           │           │           │           │
│ Research  │ Core      │ Desktop   │ Banking   │ Multi-    │ API       │
│ & Design  │ Features  │ & Payroll │ & Reports │ Entity    │ Platform  │
│           │           │           │           │           │           │
└───────────┴───────────┴───────────┴───────────┴───────────┴───────────┘
```

Note: No mobile application is planned. Phase 3 will include desktop 
applications for Windows and macOS platforms.

---

## Phase 1: Foundation (Q1 2026)

**Duration:** 12 Weeks  
**Goal:** Complete research, documentation, design, and infrastructure setup

### Milestones

| Week | Milestone | Deliverables |
|------|-----------|--------------|
| 1-2 | Project Setup | Repository, documentation, team onboarding |
| 3-4 | User Research | Interviews, surveys, persona validation |
| 5-6 | Compliance Research | 2026 tax law deep-dive, NRS API specs |
| 7-8 | UX Design | Wireframes, user flows, design system |
| 9-10 | Architecture | Technical design, database schema, API spec |
| 11-12 | Infrastructure | Cloud setup, CI/CD, development environment |

### Key Deliverables

- [x] README and project documentation
- [x] Business case document
- [x] Use case specifications
- [x] UI/UX research document
- [x] Technical architecture document
- [x] Compliance requirements document
- [ ] Figma design system
- [ ] High-fidelity mockups
- [ ] NRS API sandbox access
- [ ] AWS infrastructure provisioned
- [ ] Development team hired (4 developers minimum)

### Exit Criteria

- Design approved by stakeholders
- NRS partnership discussion initiated
- Development environment ready
- First developer commit to repository

---

## Phase 2: MVP Development (Q2 2026)

**Duration:** 12 Weeks  
**Goal:** Launch minimum viable product with core tax compliance features

### Sprint Breakdown

| Sprint | Focus | Features |
|--------|-------|----------|
| Sprint 1-2 | Auth & Setup | User registration, business setup, basic dashboard |
| Sprint 3-4 | Financial Core | Expense recording, income recording, categories |
| Sprint 5-6 | Invoicing | Invoice creation, PDF generation, customer management |
| Sprint 7-8 | E-Invoicing | NRS integration, IRN generation, QR codes |
| Sprint 9-10 | VAT & Reports | VAT tracking, P&L report, trial balance |
| Sprint 11-12 | Polish & Launch | Bug fixes, performance, launch preparation |

### MVP Feature Set

#### Included in MVP

| Feature | Priority | Status |
|---------|----------|--------|
| User authentication (email) | P0 | ✅ Complete |
| Business profile setup | P0 | ✅ Complete |
| Expense recording (manual) | P0 | ✅ Complete |
| OCR receipt scanning | P0 | ✅ Complete |
| Income recording | P0 | ✅ Complete |
| WREN expense classification | P0 | ✅ Complete |
| Invoice creation | P0 | ✅ Complete |
| NRS e-invoice submission | P0 | ✅ Complete |
| IRN & QR code embedding | P0 | ✅ Complete |
| Vendor management | P1 | ✅ Complete |
| TIN verification | P1 | ✅ Complete |
| Output VAT tracking | P0 | ✅ Complete |
| Basic Input VAT tracking | P1 | ✅ Complete |
| P&L report | P0 | ✅ Complete |
| Trial balance | P0 | ✅ Complete |
| Dashboard with alerts | P0 | ✅ Complete |
| Mobile-responsive web | P0 | ✅ Complete |
| **Multi-Currency / FX** | P1 | ✅ Complete |
| **Budget Management** | P1 | ✅ Complete |
| **SKU Feature Gating** | P0 | ✅ Complete |

#### Deferred from MVP

| Feature | Reason | Target Phase | Status |
|---------|--------|--------------|--------|
| Desktop app (Windows/macOS) | Web-first approach | Phase 3 | Planned |
| Full PAYE/Payroll | Complexity | Phase 3 | ✅ Delivered Early |
| Bank sync | Third-party dependency | Phase 4 | ✅ Delivered Early |
| Multi-entity support | Enterprise feature | Phase 5 | ✅ Delivered Early |
| Asset depreciation | Not critical for launch | Phase 4 | ✅ Delivered Early |
| Self-assessment export | Requires full year data | Phase 4 | Planned |
| Inventory management | Not core to compliance | Phase 3 | ✅ Delivered Early |
| WHT management | Lower priority | Phase 3 | ✅ Delivered Early |

Note: No mobile application is planned for any phase. The product will be 
web-only initially, with native desktop apps (Windows/macOS) in Phase 3.

### Launch Criteria

- [ ] 100 beta users onboarded
- [ ] Zero critical bugs
- [ ] NRS e-invoicing certified (or sandbox approved)
- [ ] < 3 second page load time
- [ ] 99.5% uptime for 2 weeks
- [ ] Customer support process established

---

## Phase 3: Growth Features (Q3 2026)

**Duration:** 12 Weeks  
**Goal:** Desktop app launch, payroll module, inventory management

### Key Features

| Feature | Description | Business Value |
|---------|-------------|----------------|
| **Desktop App (Windows)** | Native Windows application | Offline-capable, power users |
| **Desktop App (macOS)** | Native macOS application | Reach Mac users |
| **Offline Mode** | Record transactions without internet | Critical for Nigeria |
| **PAYE Calculator** | Full 2026 tax band implementation | Enable payroll management |
| **Employee Management** | Add employees, track salaries | Foundation for payroll |
| **Payroll Processing** | Monthly salary runs with PAYE | Reduce accountant dependence |
| **Inventory Module** | Stock tracking, low-stock alerts | SME value-add |
| **Stock Write-offs** | Tax-deductible damaged goods | Stock-to-Tax feature |
| **WHT Calculator** | Withholding tax with exemptions | Complete tax coverage |

### Desktop App Technology Stack

| Platform | Framework | Rationale |
|----------|-----------|-----------|
| Windows | Tauri + React | Lightweight, Rust-based, secure |
| macOS | Tauri + React | Cross-platform codebase |
| Sync | REST API | Real-time cloud synchronization |

### Milestones

| Week | Milestone |
|------|-----------|
| Week 1-4 | Desktop app core (auth, dashboard, expenses) |
| Week 5-8 | Payroll module development |
| Week 9-10 | Inventory module |
| Week 11-12 | Integration testing, desktop app distribution |

### Success Metrics

- 5,000 registered users
- 1,000 monthly active users
- Desktop apps: 500+ downloads
- Payroll processing: 500 employees

---

## Phase 4: Scale & Intelligence (Q4 2026)

**Duration:** 12 Weeks  
**Goal:** Banking integration, advanced reporting, automation

### Key Features

| Feature | Description | Business Value |
|---------|-------------|----------------|
| **Bank Statement Sync** | Connect to Nigerian banks | Automated reconciliation |
| **Auto-Reconciliation** | Match bank transactions to ledger | Save hours of work |
| **Balance Sheet** | Complete financial statement | Audit readiness |
| **Cash Flow Statement** | Track cash movements | Financial visibility |
| **Fixed Asset Register** | Track assets, depreciation | Tax optimization |
| **CIT Calculator** | Full corporate tax computation | Year-end compliance |
| **Self-Assessment Export** | TaxPro Max compatible format | Easy filing |
| **Audit Package Generator** | One-click audit-ready PDFs | Professional output |

### Banking Integration Partners (Target)

| Bank | API Status | Priority |
|------|------------|----------|
| GTBank | Available | P0 |
| Access Bank | Available | P0 |
| UBA | In Development | P1 |
| First Bank | Available | P1 |
| Zenith Bank | Available | P1 |

### Success Metrics

- 25,000 registered users
- 10,000 monthly active users
- 2,000 bank connections
- ₦500M transactions processed

---

## Phase 5: Enterprise (Q1 2027)

**Duration:** 12 Weeks  
**Goal:** Multi-entity support, team features, government partnerships

### Key Features

| Feature | Description | Business Value |
|---------|-------------|----------------|
| **Multi-Entity Management** | Separate ledgers per business | Holding company support |
| **Consolidated Reporting** | Cross-entity financial views | Group-level insights |
| **Team Management** | Invite users, assign roles | Collaboration |
| **Auditor Portal** | Read-only access for tax consultants | Professional workflow |
| **Approval Workflows** | Multi-level expense approvals | Enterprise controls |
| **SSO Integration** | Google/Microsoft login | Enterprise security |
| **API Access** | Third-party integrations | Platform extensibility |

### Government Partnership Deliverables

| Partner | Deliverable | Status |
|---------|-------------|--------|
| NRS | Official certification as approved software | Target |
| NITDA | Data protection compliance certification | Target |
| CBN | Financial data handling compliance | Target |
| ICAN/CITN | Professional endorsement | Target |

### Success Metrics

- 100,000 registered users
- 50,000 monthly active users
- 500 enterprise accounts
- 1 government agency deployment

---

## Phase 6: Ecosystem (Q2 2027)

**Duration:** 12+ Weeks  
**Goal:** Platform for third-party integrations, marketplace

### Key Features

| Feature | Description | Business Value |
|---------|-------------|----------------|
| **Public API** | RESTful API for integrators | Ecosystem growth |
| **Developer Portal** | API documentation, sandbox | Developer adoption |
| **App Marketplace** | Third-party add-ons | Extensibility |
| **Tax Consultant Directory** | Find verified professionals | User value-add |
| **AI Tax Advisor** | Intelligent recommendations | Differentiation |
| **Predictive Analytics** | Cash flow forecasting | Advanced insights |
| **International Expansion** | Ghana, Kenya markets | Growth |

---

## Risk Mitigation Timeline

| Risk | Mitigation | Timeline |
|------|------------|----------|
| NRS API delays | Build with mock API, maintain flexibility | Phase 1-2 |
| Low adoption | Heavy marketing, accountant partnerships | Phase 2-3 |
| Competition | Speed to market, superior UX | Phase 2 |
| Regulation changes | Modular architecture, quick updates | Ongoing |
| Technical debt | Refactoring sprints every quarter | Ongoing |

---

## Resource Requirements

### Team Growth Plan

| Phase | Engineering | Product | Design | Support | Total |
|-------|-------------|---------|--------|---------|-------|
| Phase 1 | 2 | 1 | 1 | 0 | 4 |
| Phase 2 | 4 | 1 | 1 | 1 | 7 |
| Phase 3 | 6 | 1 | 1 | 2 | 10 |
| Phase 4 | 8 | 2 | 2 | 3 | 15 |
| Phase 5 | 12 | 2 | 2 | 5 | 21 |
| Phase 6 | 15 | 3 | 3 | 8 | 29 |

### Budget Summary (₦ Millions)

| Phase | Development | Infrastructure | Marketing | Operations | Total |
|-------|-------------|----------------|-----------|------------|-------|
| Phase 1 | 20 | 5 | 2 | 3 | 30 |
| Phase 2 | 40 | 15 | 20 | 10 | 85 |
| Phase 3 | 50 | 25 | 40 | 15 | 130 |
| Phase 4 | 60 | 40 | 80 | 25 | 205 |
| Phase 5 | 80 | 60 | 150 | 40 | 330 |
| Phase 6 | 100 | 80 | 200 | 70 | 450 |

---

## Key Dependencies

### External Dependencies

| Dependency | Risk Level | Mitigation |
|------------|------------|------------|
| NRS API availability | High | Early engagement, mock API fallback |
| Bank API access | Medium | Use aggregators (Mono, Okra) |
| OCR service | Low | Multiple provider options |
| Cloud infrastructure | Low | Multi-cloud capability |

### Internal Dependencies

| Dependency | Risk Level | Mitigation |
|------------|------------|------------|
| Hiring pace | Medium | Start recruiting in Phase 1 |
| Design completion | Medium | Parallel design/dev tracks |
| Compliance expertise | High | Hire/consult tax specialists early |

---

## Success Metrics Dashboard

### North Star Metrics

| Metric | Phase 2 | Phase 4 | Phase 6 |
|--------|---------|---------|---------|
| Registered Users | 1,000 | 25,000 | 200,000 |
| Monthly Active Users | 500 | 10,000 | 80,000 |
| E-Invoices Submitted | 5,000 | 500,000 | 5,000,000 |
| Monthly Revenue | ₦5M | ₦75M | ₦400M |
| NPS Score | 40 | 55 | 70 |

### Compliance Metrics

| Metric | Target |
|--------|--------|
| E-Invoice Success Rate | 99.5% |
| Tax Calculation Accuracy | 100% |
| System Uptime | 99.9% |
| Audit Pass Rate | 100% |

---

## Governance

### Review Cadence

| Meeting | Frequency | Participants |
|---------|-----------|--------------|
| Sprint Review | Bi-weekly | Product, Engineering |
| Phase Review | Monthly | Leadership, Investors |
| Roadmap Review | Quarterly | All stakeholders |
| Board Update | Quarterly | Board, Executive team |

### Change Management

- **Minor scope changes:** Product Manager approval
- **Major scope changes:** Leadership approval + roadmap update
- **Phase changes:** Board notification required

---

## Appendix: Feature Priority Matrix

```
                    HIGH IMPACT
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          │  E-Invoicing │   Banking    │
          │  VAT Track   │   Sync       │
          │  PAYE Calc   │   Multi-     │
          │              │   Entity     │
 LOW      │──────────────┼──────────────│  HIGH
 EFFORT   │              │              │  EFFORT
          │  Dashboard   │   AI Tax     │
          │  OCR Scan    │   Advisor    │
          │  Basic       │   Predictive │
          │  Reports     │   Analytics  │
          │              │              │
          └──────────────┼──────────────┘
                         │
                    LOW IMPACT

Priority Order:
1. E-Invoicing (High Impact, Medium Effort) - MVP
2. VAT Tracking (High Impact, Low Effort) - MVP
3. OCR Scan (Medium Impact, Low Effort) - MVP
4. PAYE Calculator (High Impact, Medium Effort) - Phase 3
5. Banking Sync (High Impact, High Effort) - Phase 4
6. Multi-Entity (High Impact, High Effort) - Phase 5
```

---

*This roadmap is a living document and will be updated quarterly based on market feedback, regulatory changes, and business priorities.*

**Last Updated:** January 3, 2026  
**Next Review:** April 1, 2026
