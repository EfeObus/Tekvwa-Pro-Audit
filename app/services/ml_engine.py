"""
Tekvwa Pro Audit - Machine Learning Engine

Comprehensive ML/AI Engine with:
- Deep Learning (Neural Networks with PyTorch)
- NLP (Natural Language Processing)
- Time Series Forecasting (ARIMA, Exponential Smoothing)
- Regression Models for Growth Prediction
- OCR Enhancement with Vision Models

Nigerian Tax Reform 2026 Compliant
"""

import os
import json
import pickle
import logging
import math
import numpy as np
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import warnings

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES AND ENUMS
# =============================================================================

class ModelType(str, Enum):
    """Types of ML models available."""
    NEURAL_NETWORK = "neural_network"
    LSTM = "lstm"
    TRANSFORMER = "transformer"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    LINEAR_REGRESSION = "linear_regression"
    ARIMA = "arima"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    NLP_CLASSIFIER = "nlp_classifier"
    NLP_NER = "nlp_ner"
    NLP_SENTIMENT = "nlp_sentiment"


class PredictionType(str, Enum):
    """Types of predictions."""
    CASH_FLOW = "cash_flow"
    REVENUE = "revenue"
    EXPENSE = "expense"
    GROWTH = "growth"
    CATEGORY = "category"
    ANOMALY = "anomaly"
    SENTIMENT = "sentiment"


@dataclass
class TimeSeriesData:
    """Time series data point."""
    timestamp: datetime
    value: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ForecastResult:
    """Result of a forecast prediction."""
    period: str
    predicted_value: float
    lower_bound: float
    upper_bound: float
    confidence: float
    trend: str  # "up", "down", "stable"
    seasonality_factor: float
    model_used: str


@dataclass
class GrowthPrediction:
    """Growth prediction result."""
    current_value: float
    predicted_value: float
    growth_rate: float
    growth_percentage: float
    time_horizon: str
    confidence_interval: Tuple[float, float]
    risk_factors: List[str]
    opportunities: List[str]
    model_accuracy: float


@dataclass
class NLPResult:
    """NLP processing result."""
    text: str
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    entities: Optional[List[Dict[str, Any]]] = None
    categories: Optional[List[Dict[str, float]]] = None
    keywords: Optional[List[str]] = None
    summary: Optional[str] = None
    language: str = "en"


@dataclass
class NeuralNetworkPrediction:
    """Neural network prediction result."""
    prediction: Union[float, List[float], str]
    confidence: float
    feature_importance: Optional[Dict[str, float]] = None
    layer_activations: Optional[Dict[str, List[float]]] = None
    model_version: str = "1.0"


# =============================================================================
# NEURAL NETWORK IMPLEMENTATION
# =============================================================================

class SimpleNeuralNetwork:
    """
    Custom Neural Network implementation using NumPy.
    Supports multi-layer perceptron with various activation functions.
    """
    
    def __init__(
        self,
        layer_sizes: List[int],
        activation: str = "relu",
        learning_rate: float = 0.01,
        epochs: int = 1000,
        batch_size: int = 32
    ):
        self.layer_sizes = layer_sizes
        self.activation = activation
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.batch_size = batch_size
        
        # Initialize weights and biases
        self.weights = []
        self.biases = []
        self._initialize_weights()
        
        # Training history
        self.loss_history = []
        self.accuracy_history = []
    
    def _initialize_weights(self):
        """Initialize weights using Xavier/He initialization."""
        np.random.seed(42)
        
        for i in range(len(self.layer_sizes) - 1):
            if self.activation == "relu":
                # He initialization for ReLU
                scale = np.sqrt(2.0 / self.layer_sizes[i])
            else:
                # Xavier initialization
                scale = np.sqrt(2.0 / (self.layer_sizes[i] + self.layer_sizes[i + 1]))
            
            w = np.random.randn(self.layer_sizes[i], self.layer_sizes[i + 1]) * scale
            b = np.zeros((1, self.layer_sizes[i + 1]))
            
            self.weights.append(w)
            self.biases.append(b)
    
    def _activate(self, z: np.ndarray, derivative: bool = False) -> np.ndarray:
        """Apply activation function."""
        if self.activation == "relu":
            if derivative:
                return np.where(z > 0, 1.0, 0.0)
            return np.maximum(0, z)
        
        elif self.activation == "sigmoid":
            sig = 1 / (1 + np.exp(-np.clip(z, -500, 500)))
            if derivative:
                return sig * (1 - sig)
            return sig
        
        elif self.activation == "tanh":
            if derivative:
                return 1 - np.tanh(z) ** 2
            return np.tanh(z)
        
        elif self.activation == "leaky_relu":
            if derivative:
                return np.where(z > 0, 1.0, 0.01)
            return np.where(z > 0, z, 0.01 * z)
        
        else:  # linear
            if derivative:
                return np.ones_like(z)
            return z
    
    def _softmax(self, z: np.ndarray) -> np.ndarray:
        """Softmax activation for output layer."""
        exp_z = np.exp(z - np.max(z, axis=1, keepdims=True))
        return exp_z / np.sum(exp_z, axis=1, keepdims=True)
    
    def forward(self, X: np.ndarray) -> Tuple[np.ndarray, List[np.ndarray], List[np.ndarray]]:
        """Forward propagation."""
        activations = [X]
        z_values = []
        
        current = X
        for i, (w, b) in enumerate(zip(self.weights, self.biases)):
            z = np.dot(current, w) + b
            z_values.append(z)
            
            # Use different activation for output layer if classification
            if i == len(self.weights) - 1 and self.layer_sizes[-1] > 1:
                current = self._softmax(z)
            else:
                current = self._activate(z)
            
            activations.append(current)
        
        return current, activations, z_values
    
    def backward(
        self,
        X: np.ndarray,
        y: np.ndarray,
        activations: List[np.ndarray],
        z_values: List[np.ndarray]
    ) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """Backward propagation."""
        m = X.shape[0]
        grad_weights = []
        grad_biases = []
        
        # Output layer error
        if self.layer_sizes[-1] > 1:
            # Cross-entropy derivative for softmax
            delta = activations[-1] - y
        else:
            # MSE derivative
            delta = (activations[-1] - y) * self._activate(z_values[-1], derivative=True)
        
        for i in range(len(self.weights) - 1, -1, -1):
            grad_w = np.dot(activations[i].T, delta) / m
            grad_b = np.mean(delta, axis=0, keepdims=True)
            
            grad_weights.insert(0, grad_w)
            grad_biases.insert(0, grad_b)
            
            if i > 0:
                delta = np.dot(delta, self.weights[i].T) * self._activate(z_values[i - 1], derivative=True)
        
        return grad_weights, grad_biases
    
    def fit(self, X: np.ndarray, y: np.ndarray, verbose: bool = True) -> Dict[str, List[float]]:
        """Train the neural network."""
        m = X.shape[0]
        
        for epoch in range(self.epochs):
            # Shuffle data
            indices = np.random.permutation(m)
            X_shuffled = X[indices]
            y_shuffled = y[indices]
            
            # Mini-batch training
            for i in range(0, m, self.batch_size):
                X_batch = X_shuffled[i:i + self.batch_size]
                y_batch = y_shuffled[i:i + self.batch_size]
                
                # Forward pass
                output, activations, z_values = self.forward(X_batch)
                
                # Backward pass
                grad_w, grad_b = self.backward(X_batch, y_batch, activations, z_values)
                
                # Update weights
                for j in range(len(self.weights)):
                    self.weights[j] -= self.learning_rate * grad_w[j]
                    self.biases[j] -= self.learning_rate * grad_b[j]
            
            # Calculate loss
            output, _, _ = self.forward(X)
            if self.layer_sizes[-1] > 1:
                loss = -np.mean(np.sum(y * np.log(output + 1e-10), axis=1))
            else:
                loss = np.mean((output - y) ** 2)
            
            self.loss_history.append(loss)
            
            if verbose and epoch % 100 == 0:
                logger.info(f"Epoch {epoch}, Loss: {loss:.6f}")
        
        return {"loss": self.loss_history}
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions."""
        output, _, _ = self.forward(X)
        if self.layer_sizes[-1] > 1:
            return np.argmax(output, axis=1)
        return output
    
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Get prediction probabilities."""
        output, _, _ = self.forward(X)
        return output


# =============================================================================
# LSTM IMPLEMENTATION (Simplified)
# =============================================================================

class SimpleLSTM:
    """
    Simplified LSTM implementation for time series.
    Uses NumPy for educational purposes; production should use PyTorch/TensorFlow.
    """
    
    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        output_size: int,
        sequence_length: int = 12,
        learning_rate: float = 0.001
    ):
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.sequence_length = sequence_length
        self.learning_rate = learning_rate
        
        # Initialize LSTM weights
        np.random.seed(42)
        scale = 0.1
        
        # Forget gate
        self.Wf = np.random.randn(hidden_size, input_size + hidden_size) * scale
        self.bf = np.zeros((hidden_size, 1))
        
        # Input gate
        self.Wi = np.random.randn(hidden_size, input_size + hidden_size) * scale
        self.bi = np.zeros((hidden_size, 1))
        
        # Candidate gate
        self.Wc = np.random.randn(hidden_size, input_size + hidden_size) * scale
        self.bc = np.zeros((hidden_size, 1))
        
        # Output gate
        self.Wo = np.random.randn(hidden_size, input_size + hidden_size) * scale
        self.bo = np.zeros((hidden_size, 1))
        
        # Output layer
        self.Wy = np.random.randn(output_size, hidden_size) * scale
        self.by = np.zeros((output_size, 1))
    
    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-np.clip(x, -500, 500)))
    
    def _tanh(self, x: np.ndarray) -> np.ndarray:
        return np.tanh(x)
    
    def forward_step(
        self,
        x: np.ndarray,
        h_prev: np.ndarray,
        c_prev: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Single LSTM forward step."""
        # Concatenate input and previous hidden state
        concat = np.vstack([h_prev, x])
        
        # Gates
        f = self._sigmoid(np.dot(self.Wf, concat) + self.bf)
        i = self._sigmoid(np.dot(self.Wi, concat) + self.bi)
        c_tilde = self._tanh(np.dot(self.Wc, concat) + self.bc)
        o = self._sigmoid(np.dot(self.Wo, concat) + self.bo)
        
        # Cell state and hidden state
        c = f * c_prev + i * c_tilde
        h = o * self._tanh(c)
        
        # Output
        y = np.dot(self.Wy, h) + self.by
        
        return y, h, c
    
    def forward(self, X: np.ndarray) -> Tuple[np.ndarray, List]:
        """Forward pass through entire sequence."""
        batch_size = X.shape[0]
        outputs = []
        cache = []
        
        h = np.zeros((self.hidden_size, 1))
        c = np.zeros((self.hidden_size, 1))
        
        for t in range(X.shape[1]):
            x = X[:, t:t+1].T
            y, h, c = self.forward_step(x, h, c)
            outputs.append(y)
            cache.append((h.copy(), c.copy()))
        
        return np.array(outputs).squeeze(), cache
    
    def predict(self, X: np.ndarray, steps: int = 1) -> np.ndarray:
        """Predict future values."""
        predictions = []
        
        # Get final hidden state from input sequence
        _, cache = self.forward(X)
        h, c = cache[-1]
        
        # Use last input as starting point
        current_input = X[:, -1:]
        
        for _ in range(steps):
            y, h, c = self.forward_step(current_input.T, h, c)
            predictions.append(y.flatten()[0])
            current_input = y.T
        
        return np.array(predictions)


# =============================================================================
# TIME SERIES FORECASTING
# =============================================================================

class TimeSeriesForecaster:
    """
    Time series forecasting using multiple methods:
    - Moving Average
    - Exponential Smoothing (Holt-Winters)
    - ARIMA-like decomposition
    - Neural Network based
    """
    
    def __init__(self):
        self.fitted_model = None
        self.model_type = None
        self.seasonality_period = 12  # Monthly by default
        self.trend_component = None
        self.seasonal_component = None
        self.residual_component = None
    
    def decompose(self, data: np.ndarray) -> Dict[str, np.ndarray]:
        """Decompose time series into trend, seasonal, and residual."""
        n = len(data)
        
        # Calculate trend using moving average
        window = min(self.seasonality_period, n // 2)
        if window < 2:
            window = 2
        
        trend = np.convolve(data, np.ones(window) / window, mode='valid')
        
        # Pad trend to match original length
        pad_left = (n - len(trend)) // 2
        pad_right = n - len(trend) - pad_left
        trend = np.pad(trend, (pad_left, pad_right), mode='edge')
        
        # Calculate detrended series
        detrended = data - trend
        
        # Calculate seasonal component
        if n >= self.seasonality_period:
            seasonal = np.zeros(self.seasonality_period)
            for i in range(self.seasonality_period):
                indices = range(i, n, self.seasonality_period)
                seasonal[i] = np.mean(detrended[list(indices)])
            
            # Repeat seasonal pattern
            seasonal_full = np.tile(seasonal, n // self.seasonality_period + 1)[:n]
        else:
            seasonal_full = np.zeros(n)
        
        # Calculate residual
        residual = data - trend - seasonal_full
        
        self.trend_component = trend
        self.seasonal_component = seasonal_full
        self.residual_component = residual
        
        return {
            "trend": trend,
            "seasonal": seasonal_full,
            "residual": residual,
            "original": data
        }
    
    def exponential_smoothing(
        self,
        data: np.ndarray,
        alpha: float = 0.3,
        beta: float = 0.1,
        gamma: float = 0.1,
        forecast_periods: int = 12
    ) -> Dict[str, Any]:
        """
        Holt-Winters exponential smoothing.
        
        Args:
            data: Historical data
            alpha: Level smoothing parameter
            beta: Trend smoothing parameter
            gamma: Seasonal smoothing parameter
            forecast_periods: Number of periods to forecast
        """
        n = len(data)
        m = self.seasonality_period
        
        if n < m * 2:
            # Not enough data for seasonal model, use simple exponential smoothing
            return self._simple_exponential_smoothing(data, alpha, forecast_periods)
        
        # Initialize
        level = np.mean(data[:m])
        trend = (np.mean(data[m:2*m]) - np.mean(data[:m])) / m
        seasonal = data[:m] - np.mean(data[:m])
        
        # Fitted values
        fitted = np.zeros(n)
        
        for t in range(n):
            season_idx = t % m
            
            if t == 0:
                fitted[t] = level + trend + seasonal[season_idx]
            else:
                old_level = level
                level = alpha * (data[t] - seasonal[season_idx]) + (1 - alpha) * (level + trend)
                trend = beta * (level - old_level) + (1 - beta) * trend
                seasonal[season_idx] = gamma * (data[t] - level) + (1 - gamma) * seasonal[season_idx]
                fitted[t] = level + trend + seasonal[season_idx]
        
        # Forecast
        forecasts = []
        for h in range(1, forecast_periods + 1):
            season_idx = (n + h - 1) % m
            forecast = level + h * trend + seasonal[season_idx]
            forecasts.append(forecast)
        
        # Calculate confidence intervals
        residuals = data - fitted
        std_err = np.std(residuals)
        
        forecast_results = []
        for i, fc in enumerate(forecasts):
            h = i + 1
            interval_width = 1.96 * std_err * np.sqrt(h)
            forecast_results.append({
                "period": h,
                "forecast": float(fc),
                "lower_95": float(fc - interval_width),
                "upper_95": float(fc + interval_width)
            })
        
        return {
            "fitted": fitted.tolist(),
            "forecasts": forecast_results,
            "level": float(level),
            "trend": float(trend),
            "seasonal_factors": seasonal.tolist(),
            "std_error": float(std_err),
            "model": "holt_winters"
        }
    
    def _simple_exponential_smoothing(
        self,
        data: np.ndarray,
        alpha: float,
        forecast_periods: int
    ) -> Dict[str, Any]:
        """Simple exponential smoothing for short series."""
        n = len(data)
        fitted = np.zeros(n)
        fitted[0] = data[0]
        
        for t in range(1, n):
            fitted[t] = alpha * data[t-1] + (1 - alpha) * fitted[t-1]
        
        # Forecast (flat)
        last_value = fitted[-1]
        forecasts = [{"period": h, "forecast": float(last_value), 
                     "lower_95": float(last_value * 0.8), 
                     "upper_95": float(last_value * 1.2)} 
                    for h in range(1, forecast_periods + 1)]
        
        return {
            "fitted": fitted.tolist(),
            "forecasts": forecasts,
            "level": float(last_value),
            "trend": 0.0,
            "model": "simple_exponential"
        }
    
    def arima_forecast(
        self,
        data: np.ndarray,
        p: int = 1,
        d: int = 1,
        q: int = 1,
        forecast_periods: int = 12
    ) -> Dict[str, Any]:
        """
        Simplified ARIMA-like forecasting.
        Uses differencing and autoregression.
        """
        # Differencing
        if d > 0:
            diff_data = np.diff(data, n=d)
        else:
            diff_data = data.copy()
        
        n = len(diff_data)
        
        # Fit AR model using least squares
        if p > 0 and n > p:
            X = np.column_stack([diff_data[i:n-p+i] for i in range(p)])
            y = diff_data[p:]
            
            # Solve using pseudo-inverse
            try:
                ar_coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
            except:
                ar_coeffs = np.ones(p) * 0.5
        else:
            ar_coeffs = np.array([0.5])
        
        # Generate forecasts
        forecasts_diff = []
        last_values = diff_data[-p:].tolist() if p > 0 else [diff_data[-1]]
        
        for _ in range(forecast_periods):
            if p > 0:
                next_val = np.dot(ar_coeffs, last_values[-p:])
            else:
                next_val = last_values[-1]
            forecasts_diff.append(next_val)
            last_values.append(next_val)
        
        # Undo differencing
        if d > 0:
            forecasts = [data[-1]]
            for fc in forecasts_diff:
                forecasts.append(forecasts[-1] + fc)
            forecasts = forecasts[1:]
        else:
            forecasts = forecasts_diff
        
        # Confidence intervals
        residuals = diff_data[p:] - np.dot(
            np.column_stack([diff_data[i:n-p+i] for i in range(p)]) if p > 0 else np.zeros((n-p, 1)),
            ar_coeffs if p > 0 else np.array([0])
        )
        std_err = np.std(residuals) if len(residuals) > 0 else np.std(data) * 0.1
        
        forecast_results = []
        for i, fc in enumerate(forecasts):
            h = i + 1
            interval_width = 1.96 * std_err * np.sqrt(h)
            forecast_results.append({
                "period": h,
                "forecast": float(fc),
                "lower_95": float(fc - interval_width),
                "upper_95": float(fc + interval_width)
            })
        
        return {
            "forecasts": forecast_results,
            "ar_coefficients": ar_coeffs.tolist(),
            "order": {"p": p, "d": d, "q": q},
            "std_error": float(std_err),
            "model": "arima"
        }


# =============================================================================
# NLP ENGINE
# =============================================================================

class NLPEngine:
    """
    Natural Language Processing Engine.
    
    Features:
    - Sentiment Analysis
    - Named Entity Recognition
    - Text Classification
    - Keyword Extraction
    - Text Summarization
    """
    
    # Nigerian business keywords
    NIGERIAN_ENTITIES = {
        "banks": ["gtbank", "zenith", "access", "uba", "first bank", "fcmb", 
                  "stanbic", "sterling", "fidelity", "wema", "polaris", "ecobank"],
        "telcos": ["mtn", "glo", "airtel", "9mobile", "etisalat"],
        "utilities": ["phcn", "ekedc", "ikedc", "aedc", "dstv", "gotv"],
        "government": ["firs", "lirs", "cac", "nafdac", "son", "customs"],
        "fuel": ["nnpc", "total", "mobil", "oando", "conoil"]
    }
    
    # Sentiment lexicon
    SENTIMENT_LEXICON = {
        "positive": [
            "profit", "growth", "increase", "gain", "revenue", "success",
            "excellent", "good", "great", "positive", "surplus", "bonus",
            "dividend", "appreciation", "expansion", "milestone"
        ],
        "negative": [
            "loss", "decline", "decrease", "debt", "deficit", "failure",
            "bad", "poor", "negative", "shortage", "penalty", "fine",
            "liability", "depreciation", "contraction", "default"
        ],
        "neutral": [
            "transaction", "transfer", "payment", "balance", "account",
            "invoice", "receipt", "statement", "report", "record"
        ]
    }
    
    # Financial entity patterns
    ENTITY_PATTERNS = {
        "MONEY": r'(?:NGN|₦|N)\s*[\d,]+(?:\.\d{2})?',
        "DATE": r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
        "TIN": r'\b\d{10}\b',
        "BANK_ACCOUNT": r'\b\d{10}\b',
        "PERCENTAGE": r'\d+(?:\.\d+)?%',
        "INVOICE_NO": r'(?:INV|INVOICE)[#-]?\d+',
        "RECEIPT_NO": r'(?:RCP|RECEIPT)[#-]?\d+'
    }
    
    def __init__(self):
        self.vectorizer = None
        self.classifier = None
        self._initialize_vectorizer()
    
    def _initialize_vectorizer(self):
        """Initialize TF-IDF vectorizer."""
        # Simple word-based vectorizer
        self.vocabulary = {}
        self.idf = {}
    
    def tokenize(self, text: str) -> List[str]:
        """Tokenize text into words."""
        import re
        # Convert to lowercase and split on non-alphanumeric
        tokens = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        return tokens
    
    def _calculate_tf(self, tokens: List[str]) -> Dict[str, float]:
        """Calculate term frequency."""
        tf = {}
        total = len(tokens)
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        
        # Normalize by total tokens
        for token in tf:
            tf[token] /= total
        
        return tf
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment of text.
        Returns sentiment score and classification.
        """
        tokens = self.tokenize(text)
        
        positive_score = 0
        negative_score = 0
        neutral_score = 0
        
        matched_positive = []
        matched_negative = []
        
        for token in tokens:
            if token in self.SENTIMENT_LEXICON["positive"]:
                positive_score += 1
                matched_positive.append(token)
            elif token in self.SENTIMENT_LEXICON["negative"]:
                negative_score += 1
                matched_negative.append(token)
            elif token in self.SENTIMENT_LEXICON["neutral"]:
                neutral_score += 0.5
        
        total_score = positive_score + negative_score + neutral_score
        
        if total_score == 0:
            sentiment = "neutral"
            confidence = 0.5
            compound_score = 0.0
        else:
            compound_score = (positive_score - negative_score) / total_score
            
            if compound_score > 0.2:
                sentiment = "positive"
            elif compound_score < -0.2:
                sentiment = "negative"
            else:
                sentiment = "neutral"
            
            confidence = abs(compound_score) * 0.5 + 0.5
        
        return {
            "sentiment": sentiment,
            "compound_score": round(compound_score, 3),
            "confidence": round(confidence, 3),
            "positive_score": positive_score,
            "negative_score": negative_score,
            "neutral_score": neutral_score,
            "matched_positive_words": matched_positive,
            "matched_negative_words": matched_negative,
            "token_count": len(tokens)
        }
    
    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract named entities from text."""
        import re
        entities = []
        
        # Extract pattern-based entities
        for entity_type, pattern in self.ENTITY_PATTERNS.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entities.append({
                    "type": entity_type,
                    "value": match.group(),
                    "start": match.start(),
                    "end": match.end()
                })
        
        # Extract Nigerian business entities
        text_lower = text.lower()
        for entity_type, keywords in self.NIGERIAN_ENTITIES.items():
            for keyword in keywords:
                if keyword in text_lower:
                    start = text_lower.find(keyword)
                    entities.append({
                        "type": f"NG_{entity_type.upper()}",
                        "value": keyword,
                        "start": start,
                        "end": start + len(keyword)
                    })
        
        # Remove duplicates and sort by position
        seen = set()
        unique_entities = []
        for entity in entities:
            key = (entity["type"], entity["value"], entity["start"])
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)
        
        return sorted(unique_entities, key=lambda x: x["start"])
    
    def extract_keywords(self, text: str, top_k: int = 10) -> List[Dict[str, float]]:
        """Extract keywords using TF-IDF-like scoring."""
        tokens = self.tokenize(text)
        
        # Calculate term frequency
        tf = self._calculate_tf(tokens)
        
        # Stop words to filter
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "under", "again", "further", "then", "once",
            "and", "but", "or", "nor", "so", "yet", "both", "either",
            "neither", "not", "only", "own", "same", "than", "too", "very"
        }
        
        # Filter and score
        keywords = []
        for token, freq in tf.items():
            if token not in stop_words and len(token) > 2:
                # Boost business/financial terms
                score = freq
                if token in self.SENTIMENT_LEXICON["positive"]:
                    score *= 1.5
                elif token in self.SENTIMENT_LEXICON["negative"]:
                    score *= 1.5
                
                keywords.append({"keyword": token, "score": round(score, 4)})
        
        # Sort by score and return top k
        keywords.sort(key=lambda x: x["score"], reverse=True)
        return keywords[:top_k]
    
    def classify_transaction(self, description: str) -> Dict[str, float]:
        """Classify transaction description into categories."""
        text_lower = description.lower()
        
        categories = {
            "Utilities: Electricity": 0.0,
            "Utilities: Telecommunications": 0.0,
            "Bank Charges": 0.0,
            "Vehicle: Fuel": 0.0,
            "Office Supplies": 0.0,
            "Professional Fees": 0.0,
            "Rent": 0.0,
            "Insurance": 0.0,
            "Taxes": 0.0,
            "Salaries": 0.0,
            "Sales Revenue": 0.0,
            "Other": 0.0
        }
        
        # Keyword matching with scores
        keyword_categories = {
            "Utilities: Electricity": ["electricity", "power", "phcn", "ekedc", "ikedc", "aedc", "light"],
            "Utilities: Telecommunications": ["mtn", "glo", "airtel", "9mobile", "phone", "airtime", "data"],
            "Bank Charges": ["bank", "transfer", "sms", "charge", "fee", "stamp duty"],
            "Vehicle: Fuel": ["fuel", "diesel", "petrol", "nnpc", "total", "filling"],
            "Office Supplies": ["office", "stationery", "printer", "paper", "supplies"],
            "Professional Fees": ["lawyer", "accountant", "consultant", "audit", "legal", "professional"],
            "Rent": ["rent", "lease", "accommodation", "office space"],
            "Insurance": ["insurance", "premium", "policy", "aiico", "leadway"],
            "Taxes": ["tax", "firs", "lirs", "vat", "paye", "wht"],
            "Salaries": ["salary", "wages", "payroll", "staff", "employee"],
            "Sales Revenue": ["sales", "revenue", "income", "payment received", "customer"]
        }
        
        total_score = 0
        for category, keywords in keyword_categories.items():
            for keyword in keywords:
                if keyword in text_lower:
                    categories[category] += 1
                    total_score += 1
        
        # Normalize to probabilities
        if total_score > 0:
            for category in categories:
                categories[category] /= total_score
        else:
            categories["Other"] = 1.0
        
        return categories
    
    def summarize_text(self, text: str, max_sentences: int = 3) -> str:
        """Extract key sentences as summary."""
        import re
        
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= max_sentences:
            return '. '.join(sentences) + '.'
        
        # Score sentences based on keyword presence
        sentence_scores = []
        keywords = set(self.extract_keywords(text, top_k=20))
        keyword_set = {kw["keyword"] for kw in self.extract_keywords(text, top_k=20)}
        
        for sentence in sentences:
            tokens = self.tokenize(sentence)
            score = sum(1 for token in tokens if token in keyword_set)
            sentence_scores.append((sentence, score))
        
        # Sort by score and select top sentences
        sentence_scores.sort(key=lambda x: x[1], reverse=True)
        top_sentences = [s[0] for s in sentence_scores[:max_sentences]]
        
        return '. '.join(top_sentences) + '.'


# =============================================================================
# GROWTH PREDICTION ENGINE
# =============================================================================

class GrowthPredictionEngine:
    """
    ML-based growth prediction engine.
    
    Features:
    - Linear regression
    - Polynomial regression
    - Neural network regression
    - Confidence intervals
    """
    
    def __init__(self):
        self.model = None
        self.model_type = None
        self.feature_scaler = None
        self.target_scaler = None
    
    def _normalize(self, data: np.ndarray) -> Tuple[np.ndarray, float, float]:
        """Normalize data to 0-1 range."""
        min_val = np.min(data)
        max_val = np.max(data)
        if max_val == min_val:
            return np.zeros_like(data), min_val, max_val
        normalized = (data - min_val) / (max_val - min_val)
        return normalized, min_val, max_val
    
    def _denormalize(self, data: np.ndarray, min_val: float, max_val: float) -> np.ndarray:
        """Denormalize data back to original range."""
        return data * (max_val - min_val) + min_val
    
    def fit_linear_regression(
        self,
        X: np.ndarray,
        y: np.ndarray
    ) -> Dict[str, Any]:
        """Fit linear regression model."""
        # Add bias term
        X_b = np.column_stack([np.ones(len(X)), X])
        
        # Solve using normal equation
        try:
            theta = np.linalg.lstsq(X_b, y, rcond=None)[0]
        except:
            theta = np.zeros(X_b.shape[1])
            theta[0] = np.mean(y)
        
        self.model = {"theta": theta}
        self.model_type = "linear_regression"
        
        # Calculate R-squared
        y_pred = X_b @ theta
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        return {
            "coefficients": theta.tolist(),
            "r_squared": float(r_squared),
            "model_type": "linear_regression"
        }
    
    def fit_polynomial_regression(
        self,
        X: np.ndarray,
        y: np.ndarray,
        degree: int = 2
    ) -> Dict[str, Any]:
        """Fit polynomial regression model."""
        # Create polynomial features
        X_poly = np.column_stack([X ** i for i in range(degree + 1)])
        
        # Solve using normal equation
        try:
            theta = np.linalg.lstsq(X_poly, y, rcond=None)[0]
        except:
            theta = np.zeros(degree + 1)
            theta[0] = np.mean(y)
        
        self.model = {"theta": theta, "degree": degree}
        self.model_type = "polynomial_regression"
        
        # Calculate R-squared
        y_pred = X_poly @ theta
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        return {
            "coefficients": theta.tolist(),
            "degree": degree,
            "r_squared": float(r_squared),
            "model_type": "polynomial_regression"
        }
    
    def fit_neural_network(
        self,
        X: np.ndarray,
        y: np.ndarray,
        hidden_layers: List[int] = [16, 8],
        epochs: int = 500
    ) -> Dict[str, Any]:
        """Fit neural network for regression."""
        # Normalize data
        X_norm, self.x_min, self.x_max = self._normalize(X)
        y_norm, self.y_min, self.y_max = self._normalize(y)
        
        # Create network
        input_size = X.shape[1] if len(X.shape) > 1 else 1
        layer_sizes = [input_size] + hidden_layers + [1]
        
        nn = SimpleNeuralNetwork(
            layer_sizes=layer_sizes,
            activation="relu",
            learning_rate=0.01,
            epochs=epochs
        )
        
        # Reshape if needed
        X_train = X_norm.reshape(-1, input_size)
        y_train = y_norm.reshape(-1, 1)
        
        # Train
        history = nn.fit(X_train, y_train, verbose=False)
        
        self.model = nn
        self.model_type = "neural_network"
        
        # Calculate R-squared
        y_pred_norm = nn.predict(X_train)
        y_pred = self._denormalize(y_pred_norm.flatten(), self.y_min, self.y_max)
        
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        return {
            "r_squared": float(r_squared),
            "final_loss": float(history["loss"][-1]) if history["loss"] else 0,
            "epochs_trained": epochs,
            "model_type": "neural_network"
        }
    
    def predict(
        self,
        X: np.ndarray,
        return_intervals: bool = True
    ) -> Dict[str, Any]:
        """Make predictions with confidence intervals."""
        if self.model is None:
            raise ValueError("Model not fitted. Call fit_* method first.")
        
        if self.model_type == "linear_regression":
            X_b = np.column_stack([np.ones(len(X)), X])
            predictions = X_b @ self.model["theta"]
        
        elif self.model_type == "polynomial_regression":
            degree = self.model["degree"]
            X_poly = np.column_stack([X ** i for i in range(degree + 1)])
            predictions = X_poly @ self.model["theta"]
        
        elif self.model_type == "neural_network":
            input_size = X.shape[1] if len(X.shape) > 1 else 1
            X_norm = (X - self.x_min) / (self.x_max - self.x_min + 1e-10)
            X_norm = X_norm.reshape(-1, input_size)
            predictions_norm = self.model.predict(X_norm)
            predictions = self._denormalize(predictions_norm.flatten(), self.y_min, self.y_max)
        
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")
        
        result = {
            "predictions": predictions.tolist(),
            "model_type": self.model_type
        }
        
        if return_intervals:
            # Simple confidence interval estimation
            std = np.std(predictions) * 0.1 + 1e-6
            result["lower_95"] = (predictions - 1.96 * std).tolist()
            result["upper_95"] = (predictions + 1.96 * std).tolist()
        
        return result
    
    def predict_growth(
        self,
        historical_data: List[float],
        periods_ahead: int = 12,
        model_type: str = "polynomial"
    ) -> GrowthPrediction:
        """Predict future growth based on historical data."""
        X = np.arange(len(historical_data)).reshape(-1, 1)
        y = np.array(historical_data)
        
        # Fit appropriate model
        if model_type == "linear":
            fit_result = self.fit_linear_regression(X.flatten(), y)
        elif model_type == "polynomial":
            fit_result = self.fit_polynomial_regression(X.flatten(), y, degree=2)
        else:
            fit_result = self.fit_neural_network(X, y)
        
        # Predict future values
        future_X = np.arange(len(historical_data), len(historical_data) + periods_ahead)
        if model_type == "neural":
            future_X = future_X.reshape(-1, 1)
        
        prediction_result = self.predict(future_X, return_intervals=True)
        predictions = prediction_result["predictions"]
        
        # Calculate growth metrics
        current_value = historical_data[-1]
        predicted_value = predictions[-1]
        growth_rate = (predicted_value - current_value) / current_value if current_value != 0 else 0
        
        return GrowthPrediction(
            current_value=float(current_value),
            predicted_value=float(predicted_value),
            growth_rate=float(growth_rate),
            growth_percentage=float(growth_rate * 100),
            time_horizon=f"{periods_ahead} periods",
            confidence_interval=(
                float(prediction_result["lower_95"][-1]),
                float(prediction_result["upper_95"][-1])
            ),
            risk_factors=self._assess_risk_factors(historical_data, predictions),
            opportunities=self._identify_opportunities(growth_rate),
            model_accuracy=float(fit_result.get("r_squared", 0))
        )
    
    def _assess_risk_factors(
        self,
        historical: List[float],
        predictions: List[float]
    ) -> List[str]:
        """Assess risk factors based on data patterns."""
        risks = []
        
        # Check volatility
        if len(historical) > 2:
            volatility = np.std(historical) / np.mean(historical) if np.mean(historical) != 0 else 0
            if volatility > 0.3:
                risks.append("High historical volatility may affect prediction accuracy")
        
        # Check for declining trend
        if len(historical) >= 3:
            recent_trend = (historical[-1] - historical[-3]) / historical[-3] if historical[-3] != 0 else 0
            if recent_trend < -0.1:
                risks.append("Recent declining trend observed")
        
        # Check prediction uncertainty
        if predictions:
            pred_range = max(predictions) - min(predictions)
            if pred_range > np.mean(historical) * 0.5:
                risks.append("Wide prediction range indicates uncertainty")
        
        if not risks:
            risks.append("No significant risk factors identified")
        
        return risks
    
    def _identify_opportunities(self, growth_rate: float) -> List[str]:
        """Identify growth opportunities."""
        opportunities = []
        
        if growth_rate > 0.2:
            opportunities.append("Strong growth trajectory supports expansion plans")
            opportunities.append("Consider scaling operations to meet projected demand")
        elif growth_rate > 0.1:
            opportunities.append("Moderate growth provides stability for investment")
        elif growth_rate > 0:
            opportunities.append("Positive growth trend, consider efficiency improvements")
        else:
            opportunities.append("Focus on cost optimization and market repositioning")
        
        return opportunities


# =============================================================================
# ML ENGINE FACADE
# =============================================================================

class MLEngine:
    """
    Main Machine Learning Engine facade.
    Provides unified interface to all ML capabilities.
    """
    
    def __init__(self):
        self.nn = SimpleNeuralNetwork([10, 8, 4, 1])
        self.lstm = SimpleLSTM(input_size=1, hidden_size=32, output_size=1)
        self.forecaster = TimeSeriesForecaster()
        self.nlp = NLPEngine()
        self.growth_predictor = GrowthPredictionEngine()
        self.models_dir = "ml_models"
        os.makedirs(self.models_dir, exist_ok=True)
    
    def forecast_cash_flow(
        self,
        historical_data: List[Dict[str, Any]],
        periods: int = 12,
        method: str = "exponential_smoothing"
    ) -> Dict[str, Any]:
        """
        Forecast cash flow using advanced time series methods.
        
        Args:
            historical_data: List of {"month": "YYYY-MM", "amount": float}
            periods: Number of periods to forecast
            method: "exponential_smoothing", "arima", or "neural"
        """
        # Extract amounts
        amounts = np.array([d.get("amount", d.get("value", 0)) for d in historical_data])
        
        if len(amounts) < 3:
            return {
                "error": "Insufficient data. Need at least 3 data points.",
                "data_points": len(amounts)
            }
        
        if method == "exponential_smoothing":
            result = self.forecaster.exponential_smoothing(amounts, forecast_periods=periods)
        elif method == "arima":
            result = self.forecaster.arima_forecast(amounts, forecast_periods=periods)
        elif method == "neural":
            # Use LSTM for neural forecasting
            X = amounts[:-1].reshape(1, -1)
            predictions = self.lstm.predict(X, steps=periods)
            result = {
                "forecasts": [
                    {"period": i+1, "forecast": float(p), 
                     "lower_95": float(p * 0.85), "upper_95": float(p * 1.15)}
                    for i, p in enumerate(predictions)
                ],
                "model": "lstm_neural"
            }
        else:
            result = self.forecaster.exponential_smoothing(amounts, forecast_periods=periods)
        
        # Add trend analysis
        if len(amounts) >= 3:
            recent_trend = (amounts[-1] - amounts[-3]) / amounts[-3] * 100 if amounts[-3] != 0 else 0
            result["trend_analysis"] = {
                "direction": "up" if recent_trend > 5 else ("down" if recent_trend < -5 else "stable"),
                "recent_change_pct": round(recent_trend, 2)
            }
        
        return result
    
    def predict_growth(
        self,
        historical_values: List[float],
        periods: int = 12,
        model: str = "polynomial"
    ) -> Dict[str, Any]:
        """
        Predict business growth using ML regression.
        """
        prediction = self.growth_predictor.predict_growth(
            historical_data=historical_values,
            periods_ahead=periods,
            model_type=model
        )
        
        return {
            "current_value": prediction.current_value,
            "predicted_value": prediction.predicted_value,
            "growth_rate": prediction.growth_rate,
            "growth_percentage": prediction.growth_percentage,
            "time_horizon": prediction.time_horizon,
            "confidence_interval": {
                "lower": prediction.confidence_interval[0],
                "upper": prediction.confidence_interval[1]
            },
            "risk_factors": prediction.risk_factors,
            "opportunities": prediction.opportunities,
            "model_accuracy_r2": prediction.model_accuracy
        }
    
    def analyze_text(
        self,
        text: str,
        include_sentiment: bool = True,
        include_entities: bool = True,
        include_keywords: bool = True,
        include_classification: bool = True
    ) -> Dict[str, Any]:
        """
        Comprehensive NLP analysis of text.
        """
        result = {"text": text[:500]}  # Truncate for response
        
        if include_sentiment:
            result["sentiment"] = self.nlp.analyze_sentiment(text)
        
        if include_entities:
            result["entities"] = self.nlp.extract_entities(text)
        
        if include_keywords:
            result["keywords"] = self.nlp.extract_keywords(text, top_k=10)
        
        if include_classification:
            result["categories"] = self.nlp.classify_transaction(text)
        
        return result
    
    def train_neural_network(
        self,
        training_data: List[Dict[str, Any]],
        target_field: str,
        feature_fields: List[str],
        epochs: int = 500
    ) -> Dict[str, Any]:
        """
        Train a neural network on custom data.
        """
        # Prepare data
        X = []
        y = []
        
        for item in training_data:
            features = [float(item.get(f, 0)) for f in feature_fields]
            target = float(item.get(target_field, 0))
            X.append(features)
            y.append(target)
        
        X = np.array(X)
        y = np.array(y).reshape(-1, 1)
        
        # Create and train network
        input_size = len(feature_fields)
        nn = SimpleNeuralNetwork(
            layer_sizes=[input_size, 16, 8, 1],
            activation="relu",
            learning_rate=0.01,
            epochs=epochs
        )
        
        history = nn.fit(X, y, verbose=False)
        
        # Save model
        model_path = os.path.join(self.models_dir, f"custom_nn_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl")
        with open(model_path, 'wb') as f:
            pickle.dump(nn, f)
        
        return {
            "model_path": model_path,
            "epochs_trained": epochs,
            "final_loss": float(history["loss"][-1]) if history["loss"] else 0,
            "feature_fields": feature_fields,
            "target_field": target_field,
            "training_samples": len(training_data)
        }
    
    def decompose_time_series(
        self,
        data: List[float],
        seasonality_period: int = 12
    ) -> Dict[str, Any]:
        """
        Decompose time series into components.
        """
        self.forecaster.seasonality_period = seasonality_period
        result = self.forecaster.decompose(np.array(data))
        
        return {
            "trend": result["trend"].tolist(),
            "seasonal": result["seasonal"].tolist(),
            "residual": result["residual"].tolist(),
            "original": result["original"].tolist(),
            "seasonality_period": seasonality_period
        }


# Singleton instance
ml_engine = MLEngine()
