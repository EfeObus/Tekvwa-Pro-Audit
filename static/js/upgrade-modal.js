/**
 * TekVwarho ProAudit - Upgrade Modal Component
 * 
 * A global upgrade modal that can be triggered from anywhere in the app.
 * Shows tier comparison and allows quick upgrade initiation.
 */

(function() {
    'use strict';

    // Tier configuration with Nigerian Naira pricing
    const TIERS = {
        core: {
            name: 'Core',
            tagline: 'Essential accounting',
            monthlyPrice: 50000,
            annualPrice: 480000,
            users: 5,
            features: [
                'General Ledger',
                'Accounts Payable & Receivable',
                'Invoicing',
                'Basic Audit Trail',
                'Bank Reconciliation'
            ],
            color: 'gray'
        },
        professional: {
            name: 'Professional',
            tagline: 'Growing businesses',
            monthlyPrice: 200000,
            annualPrice: 1920000,
            users: 25,
            features: [
                'Everything in Core',
                'Fixed Assets Management',
                'Multi-entity Support',
                'Payroll Module',
                'Advanced Reporting',
                'Priority Support'
            ],
            color: 'blue',
            popular: true
        },
        enterprise: {
            name: 'Enterprise',
            tagline: 'Large organizations',
            monthlyPrice: 2000000,
            annualPrice: 19200000,
            users: 'Unlimited',
            features: [
                'Everything in Professional',
                'Full Audit System',
                'WORM Compliance Storage',
                'Forensic Analytics',
                'AI-Powered Insights',
                'Custom Integrations',
                '24/7 Dedicated Support'
            ],
            color: 'purple'
        }
    };

    // Format price in Naira
    function formatPrice(amount) {
        return '₦' + amount.toLocaleString('en-NG');
    }

    // Create modal HTML
    function createModalHTML(currentTier, featureName) {
        const tiersAbove = Object.entries(TIERS)
            .filter(([key]) => {
                const tierOrder = ['core', 'professional', 'enterprise'];
                return tierOrder.indexOf(key) > tierOrder.indexOf(currentTier);
            });

        let tiersHTML = '';
        
        if (tiersAbove.length === 0) {
            // Already on highest tier
            tiersHTML = `
                <div class="text-center py-8">
                    <div class="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <svg class="w-8 h-8 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                        </svg>
                    </div>
                    <h3 class="text-xl font-semibold text-gray-900 mb-2">You're on our top plan!</h3>
                    <p class="text-gray-600">You already have access to all features.</p>
                </div>
            `;
        } else {
            tiersHTML = tiersAbove.map(([key, tier]) => `
                <div class="border-2 rounded-xl p-6 ${tier.popular ? 'border-blue-500 relative' : 'border-gray-200'}">
                    ${tier.popular ? '<div class="absolute -top-3 left-1/2 transform -translate-x-1/2 px-3 py-1 bg-blue-500 text-white text-xs font-medium rounded-full">Recommended</div>' : ''}
                    <div class="flex items-center justify-between mb-4">
                        <div>
                            <h3 class="text-lg font-bold text-gray-900">${tier.name}</h3>
                            <p class="text-sm text-gray-500">${tier.tagline}</p>
                        </div>
                        <div class="text-right">
                            <div class="text-2xl font-bold text-gray-900">${formatPrice(tier.monthlyPrice)}</div>
                            <div class="text-xs text-gray-500">/month</div>
                        </div>
                    </div>
                    
                    <ul class="space-y-2 mb-6">
                        ${tier.features.slice(0, 4).map(f => `
                            <li class="flex items-center text-sm text-gray-600">
                                <svg class="w-4 h-4 text-green-500 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
                                </svg>
                                ${f}
                            </li>
                        `).join('')}
                        ${tier.features.length > 4 ? `<li class="text-sm text-blue-600">+${tier.features.length - 4} more features</li>` : ''}
                    </ul>
                    
                    <button onclick="TekVwarhoUpgrade.goToCheckout('${key}')" 
                            class="w-full py-3 ${tier.popular ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-gray-100 text-gray-800 hover:bg-gray-200'} font-semibold rounded-lg transition">
                        Upgrade to ${tier.name}
                    </button>
                </div>
            `).join('');
        }

        return `
            <div id="upgrade-modal-backdrop" class="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4" 
                 onclick="if(event.target === this) TekVwarhoUpgrade.close()">
                <div class="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
                    <!-- Header -->
                    <div class="p-6 border-b border-gray-200">
                        <div class="flex items-center justify-between">
                            <div>
                                <h2 class="text-2xl font-bold text-gray-900">Upgrade Your Plan</h2>
                                ${featureName ? `<p class="text-gray-600 mt-1"><span class="font-medium">${featureName}</span> requires a higher tier</p>` : ''}
                            </div>
                            <button onclick="TekVwarhoUpgrade.close()" class="text-gray-400 hover:text-gray-600">
                                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                    
                    <!-- Content -->
                    <div class="p-6">
                        <!-- Current Plan Badge -->
                        <div class="mb-6 p-3 bg-gray-50 rounded-lg flex items-center justify-between">
                            <div>
                                <span class="text-sm text-gray-500">Current Plan</span>
                                <span class="ml-2 font-semibold text-gray-900">${TIERS[currentTier]?.name || 'Trial'}</span>
                            </div>
                            <a href="/pricing" class="text-sm text-blue-600 hover:underline">Compare all plans</a>
                        </div>
                        
                        <!-- Tier Options -->
                        <div class="space-y-4">
                            ${tiersHTML}
                        </div>
                    </div>
                    
                    <!-- Footer -->
                    <div class="p-6 bg-gray-50 border-t border-gray-200 rounded-b-2xl">
                        <div class="flex items-center justify-between text-sm text-gray-500">
                            <div class="flex items-center space-x-4">
                                <span class="flex items-center">
                                    <svg class="w-4 h-4 text-green-500 mr-1" fill="currentColor" viewBox="0 0 20 20">
                                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                                    </svg>
                                    30-day guarantee
                                </span>
                                <span class="flex items-center">
                                    <svg class="w-4 h-4 text-green-500 mr-1" fill="currentColor" viewBox="0 0 20 20">
                                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                                    </svg>
                                    Cancel anytime
                                </span>
                            </div>
                            <span>
                                Questions? <a href="mailto:info@tekvwa.org" class="text-blue-600 hover:underline">Contact us</a>
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    // Global upgrade modal object
    window.TekVwarhoUpgrade = {
        currentTier: null,
        
        /**
         * Initialize the upgrade modal system
         * @param {string} tier - Current user's tier
         */
        init: function(tier) {
            this.currentTier = tier || 'core';
        },
        
        /**
         * Show the upgrade modal
         * @param {string} featureName - Optional name of feature that triggered the modal
         * @param {string} requiredTier - Optional required tier for the feature
         */
        show: function(featureName, requiredTier) {
            // Remove existing modal if any
            this.close();
            
            // Create and append modal
            const modalDiv = document.createElement('div');
            modalDiv.id = 'upgrade-modal-container';
            modalDiv.innerHTML = createModalHTML(this.currentTier, featureName);
            document.body.appendChild(modalDiv);
            
            // Prevent body scroll
            document.body.style.overflow = 'hidden';
            
            // Animate in
            requestAnimationFrame(() => {
                const backdrop = document.getElementById('upgrade-modal-backdrop');
                if (backdrop) {
                    backdrop.style.opacity = '0';
                    backdrop.style.transition = 'opacity 0.2s ease-out';
                    requestAnimationFrame(() => {
                        backdrop.style.opacity = '1';
                    });
                }
            });
        },
        
        /**
         * Close the upgrade modal
         */
        close: function() {
            const container = document.getElementById('upgrade-modal-container');
            if (container) {
                const backdrop = document.getElementById('upgrade-modal-backdrop');
                if (backdrop) {
                    backdrop.style.opacity = '0';
                    setTimeout(() => {
                        container.remove();
                        document.body.style.overflow = '';
                    }, 200);
                } else {
                    container.remove();
                    document.body.style.overflow = '';
                }
            }
        },
        
        /**
         * Navigate to checkout page with selected tier
         * @param {string} tier - Selected tier
         */
        goToCheckout: function(tier) {
            window.location.href = `/checkout?tier=${tier}`;
        },
        
        /**
         * Check if a feature requires upgrade and show modal if needed
         * @param {string} featureName - Name of the feature
         * @param {string} requiredTier - Required tier for the feature
         * @returns {boolean} - True if upgrade is required
         */
        checkFeature: function(featureName, requiredTier) {
            const tierOrder = ['core', 'professional', 'enterprise'];
            const currentIndex = tierOrder.indexOf(this.currentTier);
            const requiredIndex = tierOrder.indexOf(requiredTier);
            
            if (currentIndex < requiredIndex) {
                this.show(featureName, requiredTier);
                return true; // Upgrade required
            }
            return false; // No upgrade required
        },
        
        /**
         * Show a quick upgrade prompt (toast-style)
         * @param {string} message - Prompt message
         */
        showPrompt: function(message) {
            // Remove existing prompt
            const existing = document.getElementById('upgrade-prompt');
            if (existing) existing.remove();
            
            const prompt = document.createElement('div');
            prompt.id = 'upgrade-prompt';
            prompt.className = 'fixed bottom-4 right-4 bg-white rounded-lg shadow-lg border border-gray-200 p-4 max-w-sm z-50';
            prompt.innerHTML = `
                <div class="flex items-start space-x-3">
                    <div class="flex-shrink-0">
                        <svg class="w-6 h-6 text-blue-500" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
                        </svg>
                    </div>
                    <div class="flex-1">
                        <p class="text-sm text-gray-700">${message}</p>
                        <div class="mt-2 flex space-x-2">
                            <button onclick="TekVwarhoUpgrade.show(); document.getElementById('upgrade-prompt').remove();" 
                                    class="px-3 py-1 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700">
                                Upgrade Now
                            </button>
                            <button onclick="document.getElementById('upgrade-prompt').remove();" 
                                    class="px-3 py-1 text-gray-500 text-sm font-medium hover:text-gray-700">
                                Later
                            </button>
                        </div>
                    </div>
                    <button onclick="document.getElementById('upgrade-prompt').remove();" class="text-gray-400 hover:text-gray-600">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
            `;
            
            document.body.appendChild(prompt);
            
            // Auto-remove after 10 seconds
            setTimeout(() => {
                const el = document.getElementById('upgrade-prompt');
                if (el) el.remove();
            }, 10000);
        }
    };

    // Auto-initialize from data attribute if present
    document.addEventListener('DOMContentLoaded', function() {
        const initEl = document.querySelector('[data-sku-tier]');
        if (initEl) {
            TekVwarhoUpgrade.init(initEl.dataset.skuTier);
        }
    });
})();
