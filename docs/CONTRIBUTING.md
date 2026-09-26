# Contributing to Tekvwa Pro Audit

Thank you for considering contributing to Tekvwa Pro Audit!

**Important Notice:** This project is proprietary software owned by Tekvwa IT Solutions LTD. By contributing, you agree that your contributions become the intellectual property of Tekvwa IT Solutions LTD under the same proprietary license. Please review the LICENSE file before contributing.

This project aims to help Nigerian businesses navigate the 2026 tax reform landscape. Every contribution helps make tax compliance easier for millions of businesses.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Style Guidelines](#style-guidelines)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

---

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inclusive environment for all contributors, regardless of age, body size, disability, ethnicity, gender identity, level of experience, nationality, personal appearance, race, religion, or sexual identity and orientation.

### Expected Behavior

- Use welcoming and inclusive language
- Be respectful of differing viewpoints
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards other community members

### Unacceptable Behavior

- Trolling, insulting comments, or personal attacks
- Public or private harassment
- Publishing others' private information
- Other conduct that could be considered inappropriate

---

## How Can I Contribute?

### Reporting Bugs

Found a bug? Please help us by reporting it!

1. Check if the bug has already been reported in [Issues](https://github.com/EfeObus/Tekvwa-Pro-Audit/issues)
2. If not, create a new issue with:
   - Clear, descriptive title
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Screenshots (if applicable)
   - Environment details (OS, browser, device)

### Suggesting Features

Have an idea? We'd love to hear it!

1. Check existing [Feature Requests](https://github.com/EfeObus/Tekvwa-Pro-Audit/issues?q=is%3Aissue+label%3Aenhancement)
2. Create a new issue with:
   - Problem statement (what pain point does this solve?)
   - Proposed solution
   - Alternative solutions considered
   - Target user persona

### Improving Documentation

Documentation improvements are always welcome:

- Fix typos or unclear language
- Add examples or explanations
- Improve code comments
- Update outdated information

### Contributing Code

1. Look for issues tagged `good first issue` or `help wanted`
2. Comment on the issue to express interest
3. Fork the repository
4. Create your feature branch
5. Make your changes
6. Submit a pull request

---

## Development Setup

### Prerequisites

```bash
# Required
- Python 3.11+
- pip or pipenv
- PostgreSQL 15+
- Redis 7+
- Git

# Recommended
- VS Code with Python extension
- Docker (for local services)
```

### Getting Started

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/Tekvwa-Pro-Audit.git
cd Tekvwa-Pro-Audit

# Add upstream remote
git remote add upstream https://github.com/EfeObus/Tekvwa-Pro-Audit.git

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env

# Start development services (Docker)
docker-compose up -d

# Run database migrations
alembic upgrade head

# Start development server
uvicorn main:app --reload --port 8000
```

### Project Structure

```
Tekvwa-Pro-Audit/
├── docs/                 # Documentation
├── app/
│   ├── config.py         # Settings & environment
│   ├── database.py       # SQLAlchemy async engine
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── routers/          # FastAPI route handlers
│   ├── services/         # Business logic
│   │   └── tax_calculators/  # VAT, PAYE, CIT, WHT
│   └── tasks/            # Celery background tasks
├── templates/            # Jinja2 templates
├── static/               # CSS, JS, images
├── tests/                # Test files
├── main.py               # FastAPI entry point
├── alembic.ini           # Database migration config
├── alembic/              # Migration files
└── .github/              # GitHub workflows
```

---

## Pull Request Process

### Before Submitting

1. **Sync with upstream**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Write clean, documented code
   - Follow style guidelines
   - Add/update tests as needed

4. **Test your changes**
   ```bash
   pytest
   flake8
   mypy .
   ```

5. **Commit with a clear message**
   ```bash
   git commit -m "feat: add VAT input recovery tracking"
   ```

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, no code change
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(invoicing): add NRS e-invoice submission
fix(vat): correct input VAT recovery calculation
docs(readme): update installation instructions
test(paye): add unit tests for 2026 tax bands
```

### Pull Request Template

When creating a PR, please include:

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## How Has This Been Tested?
Describe testing approach

## Checklist
- [ ] My code follows the project style guidelines
- [ ] I have performed a self-review
- [ ] I have commented my code where needed
- [ ] I have updated documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix/feature works
- [ ] New and existing tests pass locally
```

### Review Process

1. At least one maintainer approval required
2. All CI checks must pass
3. No merge conflicts
4. Code review feedback addressed

---

## Style Guidelines

### Python

```python
# Follow PEP 8 and use type hints
# Use Black for formatting, flake8 for linting

# Good
def calculate_paye(annual_salary: Decimal) -> PAYEResult:
    """Calculate PAYE based on 2026 Nigerian tax bands."""
    # Clear, descriptive names
    pass

# Avoid
def calc(x):
    # Vague names, no type hints
    pass
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Variables | snake_case | `vat_amount` |
| Functions | snake_case | `calculate_vat()` |
| Classes | PascalCase | `InvoiceService` |
| Constants | UPPER_SNAKE_CASE | `VAT_RATE` |
| Files | snake_case | `vat_calculator.py` |
| Django Apps | lowercase | `invoicing`, `tax` |

### Code Documentation

```python
def calculate_paye(annual_salary: Decimal) -> PAYEResult:
    \"\"\"
    Calculate PAYE tax based on 2026 Nigerian tax bands.
    
    Args:
        annual_salary: Gross annual salary in Naira
        
    Returns:
        PAYEResult with monthly and annual tax amounts
        
    Example:
        >>> result = calculate_paye(Decimal('3600000'))
        >>> print(result.monthly_tax)
        Decimal('40000')
    \"\"\"
    # Implementation
    pass
```

### Multi-Tenant Entity Access (Mandatory)

Any new endpoint that takes an `entity_id` **must** use the centralized `require_entity_access`
dependency (`app/dependencies.py`) to verify the caller's organization owns that entity — this is not
optional, and PRs adding an entity-scoped endpoint without it will be asked to add it:

```python
@router.get("/{entity_id}/some-resource")
async def get_some_resource(
    entity_id: uuid.UUID,
    _entity_access: BusinessEntity = Depends(require_entity_access),  # required
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    ...
```

If `entity_id` is an optional query parameter, call the dependency inline instead (a `Depends()`
would make the parameter mandatory):

```python
if entity_id is not None:
    await require_entity_access(entity_id=entity_id, current_user=current_user, db=db)
```

Use the equivalent `require_group_access` for a `group_id`-keyed resource with its own organization
ownership. Do not use the older `verify_entity_access` helper for new code (see
`docs/TECHNICAL_ARCHITECTURE.md` §6.2 for why). See `tests/test_entity_access_isolation.py` for the
AST-based structural check and unit tests that verify this pattern, and
`tests/test_phase2_comprehensive_entity_isolation.py` for the parameterized cross-tenant regression
suite — any new entity-scoped router file added to Phase 2's migrated set should extend one of these
rather than hand-rolling a new test pattern.

### Testing Guidelines

```python
# Use pytest with descriptive test names
class TestPAYECalculator:
    def test_returns_zero_tax_for_salary_below_threshold(self):
        \"\"\"Salary below N800,000 should have zero tax.\"\"\"
        result = calculate_paye(Decimal('700000'))
        assert result.annual_tax == Decimal('0')

    def test_applies_fifteen_percent_for_second_bracket(self):
        \"\"\"Salary N800,001 to N2,400,000 should use 15% rate.\"\"\"
        # Test implementation
        pass
```

---

## Reporting Bugs

### Bug Report Template

```markdown
## Bug Description
A clear and concise description of the bug.

## Steps to Reproduce
1. Go to '...'
2. Click on '...'
3. Enter '...'
4. See error

## Expected Behavior
What you expected to happen.

## Actual Behavior
What actually happened.

## Screenshots
If applicable, add screenshots.

## Environment
- OS: [e.g., macOS 14, Windows 11, Android 13]
- Browser: [e.g., Chrome 120, Safari 17]
- App Version: [e.g., 1.0.0]

## Additional Context
Any other relevant information.
```

---

## Suggesting Features

### Feature Request Template

```markdown
## Problem Statement
What problem does this feature solve?

## Target User
Which user persona benefits from this?

## Proposed Solution
Describe the solution you'd like.

## Alternative Solutions
What alternatives have you considered?

## Additional Context
Mockups, examples, or references.
```

---

## Tax & Compliance Contributions

When contributing to tax calculation or compliance features:

1. **Reference source legislation** in comments
2. **Include calculation examples** in tests
3. **Document edge cases** thoroughly
4. **Flag for tax specialist review** if unsure

```typescript
/**
 * WHT exemption check based on 2026 Tax Reform.
 * 
 * Reference: Nigeria Tax Reform Act 2025, Section XX
 * Small business transactions under ₦2,000,000 are exempt from WHT.
 * 
 * @see COMPLIANCE_REQUIREMENTS.md Section 5
 */
function isWHTExempt(transaction: Transaction): boolean {
  // Implementation
}
```

---

## Recognition

Contributors will be recognized in:

- README.md Contributors section
- Release notes
- Annual contributor appreciation

---

## Questions?

- Create a [Discussion](https://github.com/EfeObus/Tekvwa-Pro-Audit/discussions)
- Email: info@tekvwa.org
- Community Slack: [Coming Soon]

---

Thank you for helping make tax compliance easier for Nigerian businesses!
