'use client'

import { useBilling } from '@flowglad/nextjs'

/**
 * Debug page to show FlowGlad configuration status.
 * 
 * Visit /billing/debug to see what's configured in your FlowGlad account.
 */
export default function BillingDebugPage() {
    const {
        loaded,
        errors,
        customer,
        pricingModel,
        currentSubscription,
    } = useBilling()

    if (!loaded) {
        return (
            <div className="min-h-screen bg-background text-foreground p-8">
                <h1 className="text-2xl font-bold mb-4">FlowGlad Debug</h1>
                <p>Loading...</p>
            </div>
        )
    }

    const products = pricingModel?.products || []
    const allPrices = products.flatMap(p => p.prices || [])

    return (
        <div className="min-h-screen bg-background text-foreground p-8">
            <h1 className="text-2xl font-bold mb-6">FlowGlad Configuration Debug</h1>

            {/* Errors */}
            {(errors?.length ?? 0) > 0 && (
                <div className="mb-6 p-4 bg-red-500/20 border border-red-500 rounded-lg">
                    <h2 className="text-lg font-semibold text-red-400 mb-2">Errors</h2>
                    <ul className="list-disc list-inside">
                        {errors?.map((err, i) => (
                            <li key={i} className="text-red-300">{err.message || JSON.stringify(err)}</li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Customer Info */}
            <div className="mb-6 p-4 bg-card rounded-lg border border-border">
                <h2 className="text-lg font-semibold text-info mb-2">Customer</h2>
                {customer ? (
                    <pre className="text-sm text-muted-foreground overflow-auto">
                        {JSON.stringify(customer, null, 2)}
                    </pre>
                ) : (
                    <p className="text-yellow-400">No customer data (user not authenticated or not synced)</p>
                )}
            </div>

            {/* Subscription */}
            <div className="mb-6 p-4 bg-card rounded-lg border border-border">
                <h2 className="text-lg font-semibold text-success mb-2">Current Subscription</h2>
                {currentSubscription ? (
                    <pre className="text-sm text-muted-foreground overflow-auto">
                        {JSON.stringify(currentSubscription, null, 2)}
                    </pre>
                ) : (
                    <p className="text-muted-foreground">No active subscription</p>
                )}
            </div>

            {/* Products & Prices */}
            <div className="mb-6 p-4 bg-card rounded-lg border border-border">
                <h2 className="text-lg font-semibold text-purple-400 mb-2">Products & Prices</h2>
                {products.length > 0 ? (
                    <div className="space-y-4">
                        {products.map((product: any) => (
                            <div key={product.id || product.slug} className="border border-border rounded p-3">
                                <h3 className="font-medium text-foreground">{product.name}</h3>
                                <p className="text-sm text-muted-foreground">Slug: <code className="text-purple-400">{product.slug}</code></p>
                                <p className="text-sm text-muted-foreground">{product.description}</p>
                                <div className="mt-2">
                                    <p className="text-sm font-medium text-secondary-foreground">Prices:</p>
                                    {product.prices?.length > 0 ? (
                                        <ul className="list-disc list-inside text-sm">
                                            {product.prices.map((price: any) => (
                                                <li key={price.id || price.slug} className="text-green-300">
                                                    <code>{price.slug}</code> - ${(price.unitAmount / 100).toFixed(2)}/{price.intervalUnit || 'one-time'}
                                                </li>
                                            ))}
                                        </ul>
                                    ) : (
                                        <p className="text-yellow-400 text-sm">No prices configured for this product</p>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="text-center py-8">
                        <p className="text-xl text-yellow-400 mb-2">⚠️ No Products Configured</p>
                        <p className="text-muted-foreground mb-4">
                            You need to create products and prices in your FlowGlad dashboard.
                        </p>
                        <a
                            href="https://app.flowglad.com"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600"
                        >
                            Open FlowGlad Dashboard →
                        </a>
                    </div>
                )}
            </div>

            {/* Available Price Slugs for BillingButton */}
            <div className="mb-6 p-4 bg-card rounded-lg border border-border">
                <h2 className="text-lg font-semibold text-orange-400 mb-2">Available Price Slugs</h2>
                {allPrices.length > 0 ? (
                    <div>
                        <p className="text-sm text-muted-foreground mb-2">Use one of these slugs in your BillingButton:</p>
                        <div className="flex flex-wrap gap-2">
                            {allPrices.map((price: any) => (
                                <code
                                    key={price.slug}
                                    className="px-2 py-1 bg-muted text-orange-400 rounded text-sm"
                                >
                                    {price.slug}
                                </code>
                            ))}
                        </div>
                    </div>
                ) : (
                    <p className="text-yellow-400">
                        No price slugs available. Create products in the FlowGlad dashboard first.
                    </p>
                )}
            </div>

            {/* Raw Pricing Model */}
            <details className="p-4 bg-card rounded-lg border border-border">
                <summary className="cursor-pointer text-lg font-semibold text-muted-foreground">
                    Raw Pricing Model JSON
                </summary>
                <pre className="mt-2 text-xs text-muted-foreground/70 overflow-auto max-h-96">
                    {JSON.stringify(pricingModel, null, 2)}
                </pre>
            </details>
        </div>
    )
}
