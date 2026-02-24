import { nextRouteHandler } from '@flowglad/nextjs/server'
import { flowglad } from '@/lib/flowglad'
import { NextRequest, NextResponse } from 'next/server'

/**
 * FlowGlad API route handler.
 * 
 * This catches all requests to /api/flowglad/* and delegates them to FlowGlad.
 * The getCustomerExternalId function extracts the user ID from the request.
 */
const handlers = nextRouteHandler({
    flowglad,
    getCustomerExternalId: async () => {
        return process.env.NEXT_PUBLIC_USER || 'default'
    },
    onError: (error) => {
        console.error('[Flowglad Route] Error:', error)
    },
})

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
    const { path } = await ctx.params
    console.log('[Flowglad GET]', path.join('/'))
    return handlers.GET(req, ctx)
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
    const { path } = await ctx.params
    console.log('[Flowglad POST]', path.join('/'))
    const res = await handlers.POST(req, ctx) as NextResponse
    // Log response for checkout debugging
    if (path.includes('checkout-sessions')) {
        try {
            const clone = res.clone()
            const body = await clone.json()
            console.log('[Flowglad POST] checkout response:', JSON.stringify(body).slice(0, 500))
        } catch { /* ignore */ }
    }
    return res
}
