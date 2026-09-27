// Copyright Epic Games, Inc. All Rights Reserved.

import { Config, PixelStreaming } from '@epicgames-ps/lib-pixelstreamingfrontend-ue5.4';

function initializePlayer() {
	// Example of how to set the logger level
	// Logger.SetLoggerVerbosity(10);

	// Create a config object
	const config = new Config({
		initialSettings: {
			AutoPlayVideo: true,
			AutoConnect: true,
			HoveringMouse: true,
			KeyboardInput: true,
			SuppressBrowserKeys: true,
			StartVideoMuted: true,
			WaitForStreamer: true,
		}
	});

	// Create a PixelStreaming instance and attach the video element to an existing parent div
	const videoParentElement = document.getElementById("videoParentElement");
	const pixelStreaming = new PixelStreaming(config, { videoElementParent: videoParentElement });

	// Readiness follows advancing video frames, not the iframe load event.
	const streamNotice = document.createElement('div');
	streamNotice.style.cssText = 'position:fixed;inset:0;z-index:20;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;background:#071a16;color:#e4f5ec;font:15px system-ui;text-align:center;padding:24px;box-sizing:border-box';
	const noticeText = document.createElement('div');
	const retryButton = document.createElement('button');
	retryButton.style.cssText = 'padding:10px 20px;border:1px solid #6bb698;border-radius:8px;background:#123c2e;color:white;cursor:pointer;font:inherit';
	streamNotice.append(noticeText, retryButton);
	document.body.appendChild(streamNotice);
	let streamState = '';
	let lastVideoTime = -1;
	let lastFrameAt = Date.now();
	const setStreamState = (status: string) => {
		if (streamState === status) return;
		streamState = status;
		const messages: Record<string, string> = {
			loading: '正在连接数字孪生场景，请稍候…',
			blocked: '浏览器需要您点击后才能播放场景。',
			disconnected: '场景连接已断开，请重新连接。',
			stalled: '暂未收到新的画面，可稍候或重新连接。',
			error: '场景视频加载失败，请重新连接。',
		};
		streamNotice.style.display = status === 'playing' ? 'none' : 'flex';
		noticeText.textContent = messages[status] || '';
		retryButton.textContent = status === 'blocked' ? '点击播放' : '重新连接';
		retryButton.style.display = status === 'loading' ? 'none' : 'block';
		if (window.parent !== window) window.parent.postMessage({channel:'chebaling.player.stream-status',version:1,status}, '*');
	};
	retryButton.onclick = () => {
		lastFrameAt = Date.now();
		if (streamState === 'blocked') {
			pixelStreaming.play();
		} else {
			lastVideoTime = -1;
			pixelStreaming.reconnect();
		}
		setStreamState('loading');
	};
	setStreamState('loading');
	pixelStreaming.addEventListener('streamLoading', () => {lastFrameAt = Date.now(); setStreamState('loading');});
	pixelStreaming.addEventListener('playStreamRejected', () => setStreamState('blocked'));
	pixelStreaming.addEventListener('playStreamError', () => setStreamState('error'));
	pixelStreaming.addEventListener('webRtcDisconnected', () => setStreamState('disconnected'));
	window.setInterval(() => {
		const video = videoParentElement.querySelector('video');
		if (video && !video.paused && video.readyState >= 2 && video.videoWidth > 0 && video.currentTime > 0 && video.currentTime !== lastVideoTime) {
			lastVideoTime = video.currentTime;
			lastFrameAt = Date.now();
			setStreamState('playing');
		} else if (Date.now() - lastFrameAt > 15000 && !['blocked', 'error', 'disconnected'].includes(streamState)) {
			setStreamState('stalled');
		}
	}, 1000);

	type UEAction = {
		type: "highlight" | "focus" | "focus_prediction" | "clear_highlight" | "reset_scene" | "apply_prediction";
		target_id?: string;
		focus?: boolean;
		year?: number;
		species?: string;
		dbh_m?: number;
		tree_height_m?: number;
		crown_diameter_ns_m?: number;
		crown_diameter_ew_m?: number;
		crown_volume_m3?: number;
	};
	const allowedActions = new Set(["highlight", "focus", "focus_prediction", "clear_highlight", "reset_scene", "apply_prediction"]);
	const queuedActions: UEAction[] = [];
	let dataChannelReady = false;

	const postControlStatus = (status: string, message?: string, action?: string, target_id?: string) => {
		if (window.parent === window) return;
		window.parent.postMessage({
			channel: "chebaling.player.control-status",
			version: 1,
			status,
			message,
			action,
			target_id,
		}, "*");
	};
	const isValidAction = (action: any): action is UEAction => {
		if (!action || !allowedActions.has(action.type)) return false;
		if (["highlight", "focus", "focus_prediction", "apply_prediction"].includes(action.type)) {
			if (typeof action.target_id !== "string"
				|| !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(action.target_id)) return false;
		}
		if (action.type === "apply_prediction") {
			return Number.isInteger(action.year) && action.year! >= 2026 && action.year! <= 2100
				&& typeof action.species === "string" && action.species.length <= 100
				&& ["dbh_m", "tree_height_m", "crown_diameter_ns_m",
					"crown_diameter_ew_m", "crown_volume_m3"].every((key) => {
						const value = (action as any)[key];
						return Number.isFinite(value) && value > 0;
					});
		}
		return true;
	};
	const isTrustedPortalMessage = (event: MessageEvent) => {
		if (event.source !== window.parent) return false;
		try {
			const source = new URL(event.origin);
			return (source.protocol === "http:" || source.protocol === "https:")
				&& source.hostname === window.location.hostname;
		} catch (_) {
			return false;
		}
	};
	const sendAction = (action: UEAction) => {
		const sent = dataChannelReady && pixelStreaming.emitUIInteraction({
			channel: ["apply_prediction", "focus_prediction"].includes(action.type)
				? "chebaling.prediction" : "chebaling.agent",
			version: 1,
			action,
		});
		if (!sent) {
			queuedActions.push(action);
			postControlStatus("queued");
			return;
		}
		postControlStatus("sent");
	};
	const flushQueuedActions = () => {
		const actions = queuedActions.splice(0);
		actions.forEach(sendAction);
	};
	window.addEventListener("message", (event) => {
		if (!isTrustedPortalMessage(event)) return;
		const payload = event.data;
		if (!payload || payload.channel !== "chebaling.portal.control" || payload.version !== 1) return;
		if (!Array.isArray(payload.actions)) return;
		payload.actions.filter(isValidAction).forEach(sendAction);
	});
	pixelStreaming.addEventListener("dataChannelOpen", () => {
		dataChannelReady = true;
		flushQueuedActions();
	});
	pixelStreaming.addEventListener("dataChannelClose", () => {
		dataChannelReady = false;
	});
	pixelStreaming.addResponseEventListener("chebalingAgentControl", (response: string) => {
		try {
			const payload = JSON.parse(response);
			if (payload?.channel !== "chebaling.ue.control-status") return;
			postControlStatus(payload.ok ? "executed" : "error", payload.message, payload.action, payload.target_id);
		} catch (_) {
			// Responses from unrelated UE Blueprint controls are intentionally ignored.
		}
	});

	// Streamed forest levels can restore their own UDS weather after startup.
	// Re-apply a dry midday preset over the Pixel Streaming data channel after
	// every connection and periodically while the player remains open.
	const dryDaylightCommands = [
		'set Ultra_Dynamic_Sky_C "Use System Time" False',
		'set Ultra_Dynamic_Sky_C "Animate Time Of Day" False',
		'set Ultra_Dynamic_Sky_C "Time of Day" 1200',
		"set Ultra_Dynamic_Weather_C Weather UDS_Weather_Settings'/Game/UltraDynamicSky/Blueprints/Weather_Effects/Weather_Presets/Clear_Skies.Clear_Skies'",
		'set Ultra_Dynamic_Weather_C "Cloud Coverage" 0',
		'set Ultra_Dynamic_Weather_C Rain 0',
		'set Ultra_Dynamic_Weather_C Fog 0',
		'set Ultra_Dynamic_Weather_C "Thunder/Lightning" 0',
		'r.EmitterSpawnRateScale 0',
		'r.VolumetricCloud 0',
		'r.VolumetricFog 0',
		'r.Fog 0',
		'r.LightFunctionQuality 0',
	];
	let weatherCommandTimer: number | undefined;
	const enforceDryDaylight = () => {
		dryDaylightCommands.forEach(command => pixelStreaming.emitConsoleCommand(command));
	};
	const startWeatherEnforcement = () => {
		[500, 2000, 5000, 10000].forEach(delay => window.setTimeout(enforceDryDaylight, delay));
		if (weatherCommandTimer !== undefined) window.clearInterval(weatherCommandTimer);
		weatherCommandTimer = window.setInterval(enforceDryDaylight, 10000);
	};
	pixelStreaming.addEventListener("dataChannelOpen", startWeatherEnforcement);

	// Keep the iframe focused for keyboard control without locking or hiding the mouse.
	document.body.tabIndex = -1;
	const focusPlayer = () => {
		window.focus();
		document.body.focus({ preventScroll: true });
	};
	document.addEventListener("pointerdown", focusPlayer, true);
	document.addEventListener("click", focusPlayer, true);

	// Some Chinese IMEs report physical WASD as keyCode 229. Re-emit their
	// physical key codes so Pixel Streaming sends usable UE key events.
	const movementKeys: Record<string, number> = {
		KeyW: 87,
		KeyA: 65,
		KeyS: 83,
		KeyD: 68,
	};
	const normalizeMovementKey = (event: KeyboardEvent) => {
		const keyCode = movementKeys[event.code];
		if (!keyCode || event.keyCode !== 229) return;
		event.stopImmediatePropagation();
		document.dispatchEvent(new KeyboardEvent(event.type, {
			code: event.code,
			key: event.key,
			keyCode,
			which: keyCode,
			bubbles: true,
			repeat: event.repeat,
		}));
	};
	document.addEventListener("keydown", normalizeMovementKey, true);
	document.addEventListener("keyup", normalizeMovementKey, true);

}

if (document.readyState === 'loading') {
	document.addEventListener('DOMContentLoaded', initializePlayer, { once: true });
} else {
	initializePlayer();
}
