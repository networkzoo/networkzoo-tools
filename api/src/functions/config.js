const { app } = require('@azure/functions');
const { getConfigTable } = require('../tableClient');

const PARTITION = 'config';

app.http('configGet', {
    methods: ['GET'],
    route: 'config/{id}',
    authLevel: 'anonymous',
    handler: async (request, context) => {
        const id = request.params.id;
        try {
            const client = await getConfigTable();
            const entity = await client.getEntity(PARTITION, id);
            return { jsonBody: JSON.parse(entity.data) };
        } catch (e) {
            if (e.statusCode === 404) return { status: 404, jsonBody: null };
            context.error(e);
            return { status: 500, jsonBody: { error: e.message } };
        }
    }
});

app.http('configPut', {
    methods: ['PUT'],
    route: 'config/{id}',
    authLevel: 'anonymous',
    handler: async (request, context) => {
        const id = request.params.id;
        try {
            const body = await request.json();
            const client = await getConfigTable();
            await client.upsertEntity({
                partitionKey: PARTITION,
                rowKey: id,
                data: JSON.stringify(body),
                updatedAt: new Date().toISOString(),
            }, 'Replace');
            return { jsonBody: { ok: true } };
        } catch (e) {
            context.error(e);
            return { status: 500, jsonBody: { error: e.message } };
        }
    }
});

module.exports = {};
