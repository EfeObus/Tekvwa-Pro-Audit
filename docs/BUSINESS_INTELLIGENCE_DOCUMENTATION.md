# Business Intelligence & Machine Learning Documentation

## TekVwarho ProAudit - AI-Powered Business Analytics

**Version:** 2.4.1  
**Last Updated:** January 2026  
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Features](#features)
   - [Cash Flow Forecasting](#cash-flow-forecasting)
   - [Growth Prediction](#growth-prediction)
   - [NLP Analysis](#nlp-analysis)
   - [OCR Document Processing](#ocr-document-processing)
   - [Model Training](#model-training)
4. [API Reference](#api-reference)
5. [ML Engine Technical Details](#ml-engine-technical-details)
6. [Frontend Integration](#frontend-integration)
7. [Security & Compliance](#security--compliance)
8. [Performance Considerations](#performance-considerations)
9. [Troubleshooting](#troubleshooting)

---

## Overview

TekVwarho ProAudit's Business Intelligence suite provides enterprise-grade AI and machine learning capabilities specifically designed for Nigerian businesses and tax compliance requirements. The system offers real-time analytics, predictive modeling, and intelligent document processing.

### Key Capabilities

- **Cash Flow Forecasting**: Time series prediction using Exponential Smoothing, ARIMA, and LSTM neural networks
- **Growth Prediction**: Revenue, expense, and profit forecasting with polynomial regression and neural networks
- **NLP Analysis**: Sentiment analysis, entity extraction, keyword identification, and document classification
- **OCR Processing**: Intelligent document extraction for receipts, invoices, and financial documents
- **Custom Model Training**: Train and deploy custom ML models for business-specific use cases

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    Business Insights Frontend                     │
│                  (Alpine.js + Tailwind CSS)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI ML/AI Router                          │
│                   (/api/v1/ml/* endpoints)                        │
├─────────────────────────────────────────────────────────────────┤
│  • Authentication (JWT/Cookie)                                    │
│  • Request Validation (Pydantic)                                  │
│  • Entity Access Control                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ML Engine Service                            │
│                  (app/services/ml_engine.py)                      │
├─────────────────────────────────────────────────────────────────┤
│  • SimpleNeuralNetwork (MLP)                                      │
│  • SimpleLSTM (Time Series)                                       │
│  • NLP Engine (Sentiment, NER, Classification)                    │
│  • Forecasting (Exponential Smoothing, ARIMA)                    │
│  • Model Management                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     PostgreSQL Database                           │
│                   (Transaction History)                           │
└─────────────────────────────────────────────────────────────────┘
```

### File Structure

```
app/
├── routers/
│   └── ml_ai.py              # API endpoints (1035 lines)
├── services/
│   └── ml_engine.py          # ML/AI engine (1451 lines)
│   └── advanced_ocr_service.py  # OCR processing
templates/
└── business_insights.html     # Frontend UI
docs/
└── BUSINESS_INTELLIGENCE_DOCUMENTATION.md  # This document
```

---

## Features

### Cash Flow Forecasting

Predict future cash flow patterns using historical transaction data.

#### Methods Available

| Method | Description | Best For |
|--------|-------------|----------|
| `exponential_smoothing` | Holt-Winters method with trend and seasonality | Stable data with clear patterns |
| `arima` | Auto-Regressive Integrated Moving Average | Non-stationary time series |
| `neural` | LSTM Neural Network | Complex, non-linear patterns |

#### Request Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity_id` | UUID | Required | Business entity ID |
| `periods` | int | 12 | Forecast periods (1-36 months) |
| `method` | string | exponential_smoothing | Forecasting algorithm |
| `include_seasonality` | bool | true | Include seasonal patterns |
| `include_trend` | bool | true | Include trend analysis |

#### Response Structure

```json
{
  "entity_id": "uuid",
  "forecasts": [
    {
      "period": 1,
      "forecast": 1500000.00,
      "lower_95": 1200000.00,
      "upper_95": 1800000.00
    }
  ],
  "trend_analysis": {
    "direction": "increasing",
    "strength": 0.85,
    "average_growth": 0.05
  },
  "model_used": "exponential_smoothing",
  "seasonality_period": 12,
  "confidence_level": "95%"
}
```

---

### Growth Prediction

Forecast business growth metrics using regression and neural network models.

#### Metrics Available

- **revenue**: Total income projection
- **expense**: Expenditure forecast
- **profit**: Net profit prediction

#### Models

| Model | Description | R² Accuracy |
|-------|-------------|-------------|
| `linear` | Simple linear regression | Good for steady growth |
| `polynomial` | Polynomial regression (degree 2-3) | Better for curved trends |
| `neural` | MLP Neural Network | Complex non-linear patterns |

#### Request Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity_id` | UUID | Required | Business entity ID |
| `metric` | string | revenue | Metric to predict |
| `periods` | int | 12 | Periods ahead (1-24 months) |
| `model` | string | polynomial | Prediction model |
| `include_risk_analysis` | bool | true | Include risk factors |

#### Response Structure

```json
{
  "entity_id": "uuid",
  "current_value": 5000000.00,
  "predicted_value": 6250000.00,
  "growth_rate": 0.25,
  "growth_percentage": 25.0,
  "time_horizon": "12 months",
  "confidence_interval": {
    "lower": 5500000.00,
    "upper": 7000000.00
  },
  "risk_factors": [
    "Economic volatility may impact projections",
    "Seasonal fluctuations not fully captured"
  ],
  "opportunities": [
    "Growth trajectory exceeds industry average",
    "Strong upward momentum detected"
  ],
  "model_accuracy": 0.87,
  "model_type": "polynomial"
}
```

---

### NLP Analysis

Process text content for insights, sentiment, and classification.

#### Capabilities

1. **Sentiment Analysis**: Positive/Negative/Neutral classification with confidence scores
2. **Named Entity Recognition (NER)**: Extract organizations, persons, locations, amounts, dates
3. **Keyword Extraction**: Identify key terms and topics
4. **Document Classification**: Categorize text (financial, legal, operational, etc.)

#### Request Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | Required | Text to analyze (1-10,000 chars) |
| `include_sentiment` | bool | true | Include sentiment analysis |
| `include_entities` | bool | true | Extract named entities |
| `include_keywords` | bool | true | Extract keywords |
| `include_classification` | bool | true | Classify document type |
| `include_summary` | bool | false | Generate summary |

#### Response Structure

```json
{
  "sentiment": {
    "sentiment": "positive",
    "compound_score": 0.75,
    "positive": 0.85,
    "negative": 0.05,
    "neutral": 0.10,
    "confidence": 0.92
  },
  "entities": [
    {
      "text": "Tekvwa IT Solutions LTD",
      "type": "ORGANIZATION",
      "confidence": 0.95
    },
    {
      "text": "₦500,000",
      "type": "MONEY",
      "confidence": 0.98
    }
  ],
  "keywords": [
    {
      "word": "revenue",
      "score": 0.85,
      "frequency": 3
    }
  ],
  "categories": {
    "primary": "financial",
    "confidence": 0.88,
    "secondary": ["business", "accounting"]
  },
  "text_stats": {
    "word_count": 150,
    "sentence_count": 8,
    "avg_word_length": 5.2
  }
}
```

---

### OCR Document Processing

Extract structured data from images and PDFs of financial documents.

#### Supported Document Types

| Type | Description | Extracted Fields |
|------|-------------|------------------|
| `receipt` | Purchase receipts | vendor, date, items, total, VAT |
| `invoice` | Sales/purchase invoices | invoice_number, parties, line_items |
| `bank_statement` | Bank statements | transactions, balance |
| `general` | General documents | text content |

#### Features

- **Preprocessing**: Deskewing, noise reduction, contrast enhancement
- **Multi-format**: JPG, PNG, PDF support
- **Nigerian Compliance**: Automatic VAT extraction (7.5%)
- **Azure Integration**: Optional Azure Document Intelligence for enhanced accuracy

#### Request (multipart/form-data)

| Parameter | Type | Description |
|-----------|------|-------------|
| `file` | File | Document image or PDF |
| `document_type` | string | Type of document |
| `preprocess` | bool | Apply image preprocessing |

#### Response Structure

```json
{
  "document_id": "uuid",
  "document_type": "receipt",
  "text_content": "Full extracted text...",
  "vendor": {
    "name": "ABC Supplies Ltd",
    "tin": "12345678-0001",
    "address": "123 Lagos Street"
  },
  "transaction_date": "2026-01-15",
  "receipt_number": "RCP-2026-001",
  "line_items": [
    {
      "description": "Office Supplies",
      "quantity": 5,
      "amount": 15000.00
    }
  ],
  "subtotal": 75000.00,
  "vat_rate": 7.5,
  "vat_amount": 5625.00,
  "total_amount": 80625.00,
  "confidence": 0.92,
  "processing_time_ms": 1250
}
```

---

### Model Training

Train custom ML models for business-specific predictions.

#### Model Types

| Type | Description | Use Case |
|------|-------------|----------|
| `neural_network` | Multi-layer Perceptron | Classification, regression |
| `lstm` | Long Short-Term Memory | Time series |

#### Training Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | string | Required | Unique model identifier |
| `model_type` | string | neural_network | Model architecture |
| `training_data` | array | Required | JSON array of training samples |
| `target_field` | string | Required | Field to predict |
| `feature_fields` | array | Required | Input feature fields |
| `epochs` | int | 500 | Training iterations |
| `hidden_layers` | array | [16, 8] | Network architecture |
| `learning_rate` | float | 0.01 | Optimizer learning rate |

#### Training Data Format

```json
[
  {"feature1": 100, "feature2": 50, "target": 1},
  {"feature1": 200, "feature2": 75, "target": 0},
  ...
]
```

#### Response Structure

```json
{
  "model_name": "my_classifier",
  "model_type": "neural_network",
  "status": "trained",
  "metrics": {
    "final_loss": 0.045,
    "accuracy": 0.92,
    "training_samples": 1000,
    "validation_samples": 200
  },
  "training_time_seconds": 45.2,
  "model_path": "ml_models/my_classifier.json"
}
```

---

## API Reference

### Base URL

```
/api/v1/ml/
```

### Authentication

All endpoints require authentication via:
- JWT Bearer token in `Authorization` header
- OR session cookie (`access_token`)

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/forecast/cash-flow` | Generate cash flow forecast |
| GET | `/forecast/cash-flow/{entity_id}` | Get forecast (query params) |
| POST | `/predict/growth` | Growth prediction |
| GET | `/predict/growth/{entity_id}` | Growth prediction (GET) |
| POST | `/nlp/analyze` | NLP text analysis |
| POST | `/nlp/batch-sentiment` | Batch sentiment analysis |
| POST | `/ocr/process` | OCR document processing |
| GET | `/ocr/status` | OCR service status |
| POST | `/train/neural-network` | Train custom model |
| GET | `/models` | List all models |
| GET | `/models/{model_name}` | Get model details |
| DELETE | `/models/{model_name}` | Delete model |
| POST | `/predict/{model_name}` | Make prediction with model |
| GET | `/dashboard/{entity_id}` | ML insights dashboard |
| POST | `/anomaly/detect` | Anomaly detection |

---

## ML Engine Technical Details

### Neural Network Architecture

```python
class SimpleNeuralNetwork:
    """
    Multi-Layer Perceptron implementation using NumPy.
    
    Features:
    - ReLU activation for hidden layers
    - Sigmoid/Softmax for output
    - He initialization
    - Mini-batch gradient descent
    - L2 regularization
    """
```

### LSTM Implementation

```python
class SimpleLSTM:
    """
    LSTM for time series prediction.
    
    Features:
    - Forget, input, output gates
    - Cell state management
    - Gradient clipping
    - Sequence processing
    """
```

### Forecasting Methods

#### Exponential Smoothing

Uses triple exponential smoothing (Holt-Winters) with:
- Level component (α)
- Trend component (β)
- Seasonal component (γ)

```
ŷ(t+h) = (l(t) + h*b(t)) * s(t+h-m)
```

#### ARIMA

Auto-Regressive Integrated Moving Average with:
- Autoregressive (p) terms
- Differencing (d) for stationarity
- Moving average (q) terms

---

## Frontend Integration

### Alpine.js Component

The `mlDashboard()` function provides:

```javascript
{
  // State
  selectedEntity: '',
  entities: [],
  dashboard: {},
  loading: { forecast: false, growth: false, nlp: false, ocr: false, training: false },
  notification: { show: false, message: '', type: 'success' },
  
  // Settings
  forecastSettings: { method: 'exponential_smoothing', periods: 12 },
  growthSettings: { metric: 'revenue', model: 'polynomial', periods: 12 },
  nlpSettings: { sentiment: true, entities: true, keywords: true, classification: true },
  
  // Results
  forecastResults: {},
  growthResults: {},
  nlpResults: {},
  ocrResults: {},
  
  // Methods
  async runForecast() { ... },
  async runGrowthPrediction() { ... },
  async runNLPAnalysis() { ... },
  async processOCR() { ... },
  async trainModel() { ... }
}
```

### Error Handling

The frontend implements comprehensive error handling:

1. **Toast Notifications**: Visual feedback for success/error/warning
2. **Result Error Display**: Error messages shown in results panels
3. **Loading States**: Spinner indicators during API calls
4. **Validation**: Input validation before API calls

---

## Security & Compliance

### Authentication

- JWT tokens with expiration
- Cookie-based sessions with CSRF protection
- Entity-level access control

### Data Protection

- All ML operations scoped to user's accessible entities
- Sensitive data not stored in ML models
- Audit logging of all predictions

### Nigerian Tax Compliance

- VAT calculations use 7.5% rate (2026 standard)
- Document extraction validates TIN formats
- Financial predictions consider Nigerian fiscal calendar

---

## Performance Considerations

### Optimization Tips

1. **Batch Processing**: Use batch endpoints for multiple items
2. **Caching**: Dashboard results are cached briefly
3. **Data Limits**: Keep training data under 10,000 samples
4. **Model Size**: Limit hidden layers to 3-4 for web deployment

### Resource Usage

| Operation | Typical Time | Memory |
|-----------|--------------|--------|
| Forecast (12 months) | 100-500ms | ~50MB |
| Growth Prediction | 50-200ms | ~30MB |
| NLP Analysis | 20-100ms | ~20MB |
| OCR Processing | 500-3000ms | ~100MB |
| Model Training | 5-60s | ~200MB |

---

## Troubleshooting

### Common Issues

#### 1. "Not authenticated" (401 Error)

**Cause**: Session expired or not logged in

**Solution**: 
- Log in again
- Check browser cookies are enabled
- Verify JWT token is valid

#### 2. "Entity not found" (404 Error)

**Cause**: Invalid entity ID or no access

**Solution**:
- Select a valid entity from dropdown
- Check user permissions for entity

#### 3. Forecast returns empty results

**Cause**: Insufficient historical data

**Solution**:
- Ensure entity has at least 3 months of transactions
- System uses demo data if real data is insufficient

#### 4. NLP analysis validation error (422)

**Cause**: Invalid or missing text input

**Solution**:
- Provide text content (1-10,000 characters)
- Check for special characters causing issues

#### 5. OCR processing fails

**Cause**: Invalid file format or corrupted image

**Solution**:
- Use JPG, PNG, or PDF format
- Ensure image is clear and readable
- File size should be under 10MB

### Debug Mode

Enable verbose logging in `.env`:

```
LOG_LEVEL=DEBUG
SQL_ECHO=true
```

### Support

For issues not covered here:
- Check server logs: `logs/app.log`
- Review browser console for frontend errors
- Contact support with entity ID and error message

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.4.1 | Jan 2026 | Added error handling to frontend |
| 2.4.0 | Jan 2026 | Initial ML/AI suite release |
| 2.3.0 | Dec 2025 | NLP engine enhancements |
| 2.2.0 | Nov 2025 | OCR processing added |
| 2.1.0 | Oct 2025 | Cash flow forecasting |
| 2.0.0 | Sep 2025 | ML engine foundation |

---

*© 2026 TekVwarho ProAudit. All rights reserved.*
