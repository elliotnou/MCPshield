'use client'

import { useState } from 'react'
import { useCredits } from '@/lib/use-credits'
import { Coins, Plus, Sparkles } from 'lucide-react'

interface BillingButtonProps {
    className?: string
    showBalance?: boolean
}

export function BillingButton({
    className = '',
    showBalance = true,
}: BillingButtonProps) {
    const { balance, purchaseCredits } = useCredits()
    const [showPurchase, setShowPurchase] = useState(false)
    const [purchasing, setPurchasing] = useState(false)

    const handleTestPurchase = async () => {
        setPurchasing(true)
        try {
            await purchaseCredits(100)
            setShowPurchase(false)
        } catch {
            // error handled in hook
        } finally {
            setPurchasing(false)
        }
    }

    return (
        <div className={`relative ${className}`}>
            <button
                onClick={() => setShowPurchase(!showPurchase)}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full glass border border-border/50 hover:border-primary/40 transition-colors text-sm"
            >
                <Coins className="w-3.5 h-3.5 text-amber-400" />
                <span className="font-bold text-foreground">{balance}</span>
                <span className="text-muted-foreground text-xs">credits</span>
            </button>

            {showPurchase && (
                <div className="absolute right-0 top-full mt-2 w-72 p-4 rounded-xl card-glass border border-border/50 shadow-2xl z-50 space-y-3">
                    <div className="flex items-center justify-between">
                        <h4 className="text-sm font-bold text-foreground">Credits</h4>
                        <span className="text-xs text-muted-foreground">
                            Balance: <strong className="text-foreground">{balance}</strong>
                        </span>
                    </div>

                    <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 space-y-1">
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-bold text-foreground flex items-center gap-1.5">
                                <Sparkles className="w-3.5 h-3.5 text-primary" />
                                100 Credits
                            </span>
                        </div>
                        <p className="text-[11px] text-muted-foreground">
                            1 credit per API tool generated
                        </p>
                    </div>

                    <button
                        onClick={handleTestPurchase}
                        disabled={purchasing}
                        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white font-semibold text-sm transition-all disabled:opacity-50"
                    >
                        <Plus className="w-4 h-4" />
                        {purchasing ? 'Adding...' : 'Add 100 Credits'}
                    </button>
                </div>
            )}
        </div>
    )
}
