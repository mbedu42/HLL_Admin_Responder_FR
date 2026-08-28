'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const { formatRemainingTime, queryCrcon, renderStatus } = require('../index');

test('formatRemainingTime formats CRCON seconds as HH:MM:SS', () => {
    assert.equal(formatRemainingTime(5_437, '--:--:--'), '01:30:37');
    assert.equal(formatRemainingTime(0, '--:--:--'), '00:00:00');
});

test('formatRemainingTime uses the configured fallback for invalid values', () => {
    assert.equal(formatRemainingTime(undefined, 'inconnu'), 'inconnu');
    assert.equal(formatRemainingTime(-1, 'inconnu'), 'inconnu');
    assert.equal(formatRemainingTime('invalid', 'inconnu'), 'inconnu');
});

test('renderStatus inserts the remaining time placeholder', () => {
    const status = renderStatus(
        '🎮{players}/{maxPlayers} ⏳{timeRemaining} 📍{map}',
        {
            map: 'Carentan',
            players: 75,
            maxPlayers: 100,
            timeRemaining: '00:42:15',
        },
    );

    assert.equal(status, '🎮75/100 ⏳00:42:15 📍Carentan');
});

test('queryCrcon reads the remaining round time from public info', async (context) => {
    context.mock.method(global, 'fetch', async () => ({
        ok: true,
        json: async () => ({
            failed: false,
            result: {
                current_map: { map: { map: { shortname: 'Kharkov' } } },
                player_count: 81,
                max_player_count: 100,
                time_remaining: 3_625,
            },
        }),
    }));

    const state = await queryCrcon({
        crcon: {
            baseUrl: 'http://127.0.0.1:7010',
            publicInfoPath: '/api/get_public_info',
            timeoutMs: 5_000,
        },
    });

    assert.deepEqual(state, {
        map: 'Kharkov',
        players: 81,
        maxPlayers: 100,
        timeRemainingSeconds: 3_625,
    });
});
