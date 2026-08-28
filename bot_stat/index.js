'use strict';

const { Client, GatewayIntentBits, ActivityType, Events } = require('discord.js');
const Gamedig = require('gamedig');

const CONFIG_ENV_NAME = 'BOT_STAT_CONFIG_JSON';
const MIN_REFRESH_INTERVAL_MS = 15_000;
const clients = new Map();

const builtInDefaults = {
    refreshIntervalMs: 45_000,
    maxAttempts: 3,
    fallbackMaxPlayers: 100,
    maxMapLength: 16,
    unknownMapText: 'Map Inconnue',
    unknownTimeText: '--:--:--',
    statusTemplate: '🎮{players}/{maxPlayers} ⏳{timeRemaining} 📍{map}',
    unavailableText: '🔴 Serveur indisponible',
    onlineStatus: 'online',
    offlineStatus: 'dnd',
};

const supportedSources = new Set(['gamedig', 'crcon']);

function loadConfiguration() {
    const rawConfig = process.env[CONFIG_ENV_NAME];

    if (!rawConfig) {
        throw new Error(`${CONFIG_ENV_NAME} is missing or empty`);
    }

    let parsed;
    try {
        parsed = JSON.parse(rawConfig);
    } catch (error) {
        throw new Error(`${CONFIG_ENV_NAME} is not valid JSON: ${error.message}`);
    }

    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error(`${CONFIG_ENV_NAME} must contain a JSON object`);
    }

    if (!Array.isArray(parsed.servers)) {
        throw new Error(`${CONFIG_ENV_NAME}.servers must be an array`);
    }

    const defaults = {
        ...builtInDefaults,
        ...(parsed.defaults || {}),
    };
    const enabledServers = parsed.servers.filter((server) => server.enabled !== false);
    const identifiers = new Set();

    return enabledServers.map((server, index) => {
        const location = `servers[${index}]`;
        const config = {
            ...defaults,
            ...server,
            source: server.source || 'gamedig',
            game: {
                ...(server.game || {}),
            },
            crcon: {
                ...(server.crcon || {}),
            },
        };

        assertNonEmptyString(config.id, `${location}.id`);
        if (identifiers.has(config.id)) {
            throw new Error(`Duplicate server id: ${config.id}`);
        }
        identifiers.add(config.id);

        assertNonEmptyString(config.discordToken, `${location}.discordToken`);
        if (!supportedSources.has(config.source)) {
            throw new Error(`${location}.source must be "gamedig" or "crcon"`);
        }

        if (config.source === 'gamedig') {
            assertNonEmptyString(config.game.type, `${location}.game.type`);
            assertNonEmptyString(config.game.host, `${location}.game.host`);
            assertIntegerInRange(config.game.queryPort, 1, 65_535, `${location}.game.queryPort`);
        } else {
            assertHttpUrl(config.crcon.baseUrl, `${location}.crcon.baseUrl`);
            config.crcon.publicInfoPath = config.crcon.publicInfoPath || '/api/get_public_info';
            config.crcon.timeoutMs = config.crcon.timeoutMs || 5_000;
            assertNonEmptyString(config.crcon.publicInfoPath, `${location}.crcon.publicInfoPath`);
            assertIntegerInRange(
                config.crcon.timeoutMs,
                500,
                60_000,
                `${location}.crcon.timeoutMs`,
            );
        }
        assertIntegerInRange(
            config.refreshIntervalMs,
            MIN_REFRESH_INTERVAL_MS,
            86_400_000,
            `${location}.refreshIntervalMs`,
        );
        assertIntegerInRange(config.maxAttempts, 1, 10, `${location}.maxAttempts`);
        assertIntegerInRange(config.fallbackMaxPlayers, 1, 10_000, `${location}.fallbackMaxPlayers`);
        assertIntegerInRange(config.maxMapLength, 1, 64, `${location}.maxMapLength`);
        assertNonEmptyString(config.statusTemplate, `${location}.statusTemplate`);
        assertNonEmptyString(config.unknownTimeText, `${location}.unknownTimeText`);
        assertNonEmptyString(config.unavailableText, `${location}.unavailableText`);

        return config;
    });
}

function assertNonEmptyString(value, name) {
    if (typeof value !== 'string' || value.trim() === '') {
        throw new Error(`${name} must be a non-empty string`);
    }
}

function assertIntegerInRange(value, minimum, maximum, name) {
    if (!Number.isInteger(value) || value < minimum || value > maximum) {
        throw new Error(`${name} must be an integer between ${minimum} and ${maximum}`);
    }
}

function assertHttpUrl(value, name) {
    assertNonEmptyString(value, name);

    try {
        const url = new URL(value);
        if (!['http:', 'https:'].includes(url.protocol)) {
            throw new Error('unsupported protocol');
        }
    } catch {
        throw new Error(`${name} must be a valid HTTP or HTTPS URL`);
    }
}

function renderStatus(template, values) {
    return template.replace(
        /\{(map|players|maxPlayers|timeRemaining|id)\}/g,
        (_, key) => String(values[key]),
    );
}

function formatRemainingTime(value, unavailableText) {
    if (value === null || value === undefined || value === '') {
        return unavailableText;
    }

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue) || numericValue < 0) {
        return unavailableText;
    }

    const totalSeconds = Math.floor(numericValue);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return [hours, minutes, seconds]
        .map((part) => String(part).padStart(2, '0'))
        .join(':');
}

function truncateText(value, maximumLength) {
    const characters = Array.from(String(value));
    if (characters.length <= maximumLength) {
        return characters.join('');
    }

    return `${characters.slice(0, maximumLength - 1).join('')}…`;
}

async function queryGameDig(config) {
    const state = await Gamedig.query({
            type: config.game.type,
            host: config.game.host,
            port: config.game.queryPort,
            maxAttempts: config.maxAttempts,
    });

    return {
        map: state.map,
        players: Array.isArray(state.players) ? state.players.length : 0,
        maxPlayers: state.maxplayers,
        timeRemainingSeconds: state.raw?.timeleft,
    };
}

async function queryCrcon(config) {
    const baseUrl = config.crcon.baseUrl.endsWith('/')
        ? config.crcon.baseUrl
        : `${config.crcon.baseUrl}/`;
    const endpoint = new URL(config.crcon.publicInfoPath.replace(/^\//, ''), baseUrl);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), config.crcon.timeoutMs);

    try {
        const response = await fetch(endpoint, { signal: controller.signal });
        if (!response.ok) {
            throw new Error(`CRCON returned HTTP ${response.status}`);
        }

        const payload = await response.json();
        if (payload.failed || !payload.result) {
            throw new Error(payload.error || 'CRCON returned no public server information');
        }

        const result = payload.result;
        const currentMap = result.current_map?.map;

        return {
            map:
                currentMap?.map?.shortname ||
                currentMap?.map?.pretty_name ||
                currentMap?.pretty_name ||
                currentMap?.id,
            players: result.player_count,
            maxPlayers: result.max_player_count,
            timeRemainingSeconds: result.time_remaining,
        };
    } finally {
        clearTimeout(timeout);
    }
}

async function queryServer(config) {
    if (config.source === 'crcon') {
        return queryCrcon(config);
    }

    return queryGameDig(config);
}

async function queryAndUpdate(client, config) {
    try {
        const state = await queryServer(config);

        const values = {
            id: config.id,
            map: truncateText(state.map || config.unknownMapText, config.maxMapLength),
            players: Number.isInteger(state.players) ? state.players : 0,
            maxPlayers: state.maxPlayers || config.fallbackMaxPlayers,
            timeRemaining: formatRemainingTime(
                state.timeRemainingSeconds,
                config.unknownTimeText,
            ),
        };
        const statusText = renderStatus(config.statusTemplate, values);

        client.user.setPresence({
            activities: [{ name: statusText, type: ActivityType.Custom }],
            status: config.onlineStatus,
        });

        console.log(`[${config.id}] Status updated: ${statusText}`);
    } catch (error) {
        console.error(`[${config.id}] Game server query failed: ${error.message}`);

        client.user.setPresence({
            activities: [{ name: config.unavailableText, type: ActivityType.Custom }],
            status: config.offlineStatus,
        });
    }
}

function scheduleUpdates(client, config) {
    let stopped = false;
    let timer;

    const run = async () => {
        await queryAndUpdate(client, config);
        if (!stopped) {
            timer = setTimeout(run, config.refreshIntervalMs);
        }
    };

    run().catch((error) => {
        console.error(`[${config.id}] Unexpected update error: ${error.message}`);
    });

    return () => {
        stopped = true;
        if (timer) {
            clearTimeout(timer);
        }
    };
}

async function startServerBot(config) {
    const client = new Client({ intents: [GatewayIntentBits.Guilds] });
    const runtime = { client, stopUpdates: () => {} };
    clients.set(config.id, runtime);

    client.once(Events.ClientReady, () => {
        console.log(`[${config.id}] Discord bot connected as ${client.user.tag}`);
        runtime.stopUpdates = scheduleUpdates(client, config);
    });

    client.on('error', (error) => {
        console.error(`[${config.id}] Discord client error: ${error.message}`);
    });

    try {
        await client.login(config.discordToken);
    } catch (error) {
        clients.delete(config.id);
        client.destroy();
        throw new Error(`[${config.id}] Discord login failed: ${error.message}`);
    }
}

async function shutdown(signal) {
    console.log(`Received ${signal}; stopping ${clients.size} bot(s)`);

    for (const { client, stopUpdates } of clients.values()) {
        stopUpdates();
        client.destroy();
    }

    clients.clear();
}

async function main() {
    const serverConfigs = loadConfiguration();

    if (serverConfigs.length === 0) {
        console.log('No enabled servers are configured; nothing to start');
        return;
    }

    const results = await Promise.allSettled(serverConfigs.map(startServerBot));
    const failures = results.filter((result) => result.status === 'rejected');

    for (const failure of failures) {
        console.error(failure.reason.message);
    }

    if (failures.length === results.length) {
        throw new Error('All configured Discord bots failed to start');
    }

    console.log(`${results.length - failures.length}/${results.length} bot(s) started`);
}

if (require.main === module) {
    process.once('SIGTERM', () => {
        shutdown('SIGTERM').finally(() => process.exit(0));
    });

    process.once('SIGINT', () => {
        shutdown('SIGINT').finally(() => process.exit(0));
    });

    main().catch((error) => {
        console.error(`Startup failed: ${error.message}`);
        process.exit(1);
    });
}

module.exports = {
    formatRemainingTime,
    queryCrcon,
    renderStatus,
};
