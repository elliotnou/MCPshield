import { FlowgladServer } from '@flowglad/nextjs/server'

/**
 * FlowGlad server factory function.
 * 
 * @param customerExternalId - Your app's user/organization ID (NOT Flowglad's customer ID)
 * @returns FlowgladServer instance configured for this customer
 */
export const flowglad = (customerExternalId: string) => {
    return new FlowgladServer({
        customerExternalId,
        getCustomerDetails: async (customerExternalId) => {
            // User lookup — for now single-user system
            return {
                email: `${customerExternalId}@myme.local`,
                name: customerExternalId,
            }
        },
    })
}
