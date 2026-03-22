import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

// ─────────────────────────────────────────
// API 기본 URL 설정
// ─────────────────────────────────────────
export const API_BASE = 'http://localhost:8000';

// ─────────────────────────────────────────
// 인증 토큰 저장 (AsyncStorage → 앱 재시작 후에도 유지)
// ─────────────────────────────────────────
const TOKEN_KEY = 'auth_token';
let _token: string | null = null;

export const setToken = async (t: string) => {
  _token = t;
  await AsyncStorage.setItem(TOKEN_KEY, t);
};

export const loadToken = async (): Promise<string | null> => {
  const stored = await AsyncStorage.getItem(TOKEN_KEY);
  if (stored) _token = stored;
  return stored;
};

export const getToken = () => _token;

export const clearToken = async () => {
  _token = null;
  await AsyncStorage.removeItem(TOKEN_KEY);
};

function authHeaders(): Record<string, string> {
  return _token ? { Authorization: `Bearer ${_token}` } : {};
}

// ─────────────────────────────────────────
// 인증
// ─────────────────────────────────────────
export async function apiLogin(email: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE}/auth/login-json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(err.detail ?? '로그인 실패');
  }
  const data = await res.json() as { access_token: string };
  return data.access_token;
}

export async function apiRegister(username: string, email: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(err.detail ?? '회원가입 실패');
  }
}

export async function apiGetMe(): Promise<{ id: number; username: string; email: string; created_at: string }> {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: authHeaders() });
  if (!res.ok) throw new Error('사용자 정보 조회 실패');
  return res.json();
}

// ─────────────────────────────────────────
// 영상 업로드 (웹 + 네이티브 모두 지원)
// 웹: blob URI → fetch → File 객체 → FormData
// 네이티브: { uri, name, type } → FormData (RN 전용)
// ─────────────────────────────────────────
export async function apiUploadVideo(
  uri: string,
  mimeType?: string,
  fileName?: string,
): Promise<{ video_id: number; filename: string }> {
  // 확장자 결정
  const ext = mimeType === 'video/quicktime' ? '.mov'
            : mimeType === 'video/mp4'       ? '.mp4'
            : '.mp4';

  // 파일명 결정
  let name = fileName ?? uri.split('/').pop() ?? `video${ext}`;
  if (!name.includes('.')) name = `${name}${ext}`;

  const type = mimeType ?? 'video/mp4';

  // FormData 구성 (플랫폼별 분기)
  const formData = new FormData();

  if (Platform.OS === 'web') {
    // ── 웹 환경: blob URI를 실제 File 객체로 변환 ──
    const response = await fetch(uri);
    const blob = await response.blob();
    const file = new File([blob], name, { type });
    formData.append('file', file);
  } else {
    // ── 네이티브(iOS/Android): RN 전용 패턴 ──
    formData.append('file', {
      uri: uri,
      name: name,
      type: type,
    } as any);
  }

  // fetch로 업로드 (웹 + 네이티브 모두 호환)
  const headers: Record<string, string> = {};
  if (_token) {
    headers['Authorization'] = `Bearer ${_token}`;
  }
  // Content-Type은 설정하지 않음 → fetch가 자동으로 multipart boundary 설정

  const res = await fetch(`${API_BASE}/upload-video/`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!res.ok) {
    let msg = `업로드 실패 (${res.status})`;
    try {
      const err = await res.json() as { detail?: unknown };
      const detail = err.detail;
      if (typeof detail === 'string') msg = detail;
      else if (detail) msg = JSON.stringify(detail);
    } catch { /* 기본 메시지 사용 */ }
    throw new Error(msg);
  }

  return res.json();
}


// ─────────────────────────────────────────
// 영상 분석 작업
// ─────────────────────────────────────────
export type PoseStats = {
  cadence: number;          // 케이던스 (걸음/분)
  v_oscillation: number;    // 수직 진동 (cm)
  avg_impact_z: number;     // 평균 착지 z값
  asymmetry: number;        // 좌우 비대칭 (%)
  elbow_angle: number;      // 팔꿈치 각도 (도)
};

export type AnalysisJob = {
  id: number;
  video_id: number;
  status: string;
  result_json: string | null;
  created_at: string;
};

export async function apiCreateAnalysisJob(videoId: number): Promise<AnalysisJob> {
  const res = await fetch(`${API_BASE}/analysis-jobs/`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_id: videoId }),
  });
  if (!res.ok) throw new Error('분석 작업 생성 실패');
  return res.json();
}

export async function apiGetAnalysisJob(jobId: number): Promise<AnalysisJob> {
  const res = await fetch(`${API_BASE}/analysis-jobs/${jobId}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('분석 작업 조회 실패');
  return res.json();
}

export async function apiListAnalysisJobs(): Promise<AnalysisJob[]> {
  const res = await fetch(`${API_BASE}/analysis-jobs/`, { headers: authHeaders() });
  if (!res.ok) throw new Error('분석 기록 조회 실패');
  return res.json();
}

// ─────────────────────────────────────────
// 숏폼 작업
// ─────────────────────────────────────────
export type ShortformJob = {
  id: number;
  status: string;
  output_filename: string | null;
  style: string;
  duration_sec: number;
  video_ids_json: string | null;
  created_at: string;
};

export async function apiCreateShortformJob(
  videoIds: number[], style: string, durationSec: number
): Promise<ShortformJob> {
  const res = await fetch(`${API_BASE}/shortform-jobs/`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_ids: videoIds, style, duration_sec: durationSec }),
  });
  if (!res.ok) throw new Error('숏폼 작업 생성 실패');
  return res.json();
}

export async function apiGetShortformJob(jobId: number): Promise<ShortformJob> {
  const res = await fetch(`${API_BASE}/shortform-jobs/${jobId}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('숏폼 작업 조회 실패');
  return res.json();
}

export async function apiListShortformJobs(): Promise<ShortformJob[]> {
  const res = await fetch(`${API_BASE}/shortform-jobs/`, { headers: authHeaders() });
  if (!res.ok) throw new Error('숏폼 기록 조회 실패');
  return res.json();
}

// ─────────────────────────────────────────
// 베스트 컷 작업
// ─────────────────────────────────────────
export type BestcutJob = {
  id: number;
  status: string;
  result_json: string | null;
  photo_count: number;
  video_ids_json: string | null;
  created_at: string;
};

export async function apiCreateBestcutJob(
  videoIds: number[], photoCount: number
): Promise<BestcutJob> {
  const res = await fetch(`${API_BASE}/bestcut-jobs/`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_ids: videoIds, photo_count: photoCount }),
  });
  if (!res.ok) throw new Error('베스트 컷 작업 생성 실패');
  return res.json();
}

export async function apiGetBestcutJob(jobId: number): Promise<BestcutJob> {
  const res = await fetch(`${API_BASE}/bestcut-jobs/${jobId}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('베스트 컷 작업 조회 실패');
  return res.json();
}

export async function apiListBestcutJobs(): Promise<BestcutJob[]> {
  const res = await fetch(`${API_BASE}/bestcut-jobs/`, { headers: authHeaders() });
  if (!res.ok) throw new Error('베스트 컷 기록 조회 실패');
  return res.json();
}

// ─────────────────────────────────────────
// 코칭 영상 작업
// ─────────────────────────────────────────
export type CoachingJob = {
  id: number;
  video_id: number;
  coaching_text: string | null;
  status: string;
  output_filename: string | null;
  created_at: string;
};

export async function apiCreateCoachingJob(
  videoId: number,
  coachingText: string,
  analysisJobId?: number
): Promise<CoachingJob> {
  const res = await fetch(`${API_BASE}/coaching-jobs/`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      video_id: videoId,
      coaching_text: coachingText,
      analysis_job_id: analysisJobId ?? null,
    }),
  });
  if (!res.ok) throw new Error('코칭 영상 작업 생성 실패');
  return res.json();
}

export async function apiGetCoachingJob(jobId: number): Promise<CoachingJob> {
  const res = await fetch(`${API_BASE}/coaching-jobs/${jobId}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('코칭 영상 작업 조회 실패');
  return res.json();
}


// ─────────────────────────────────────────
// UTC 날짜 파싱 유틸 (서버가 timezone 없이 UTC 반환하는 문제 대응)
// ─────────────────────────────────────────
export function parseUtcDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const s = iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z';
  return new Date(s);
}

export function formatKoreanTime(iso: string | null | undefined): string {
  const d = parseUtcDate(iso);
  if (!d) return '-';
  return d.toLocaleString('ko-KR');
}

// ─────────────────────────────────────────
// 작업 완료까지 폴링
// ─────────────────────────────────────────
export async function pollUntilDone<T extends { status: string }>(
  fetchFn: () => Promise<T>,
  intervalMs = 2000,
  timeoutMs = 300000,  // 5분 (영상 처리는 시간이 걸릴 수 있음)
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  while (true) {
    const job = await fetchFn();
    if (job.status === 'done') return job;
    if (job.status === 'failed') throw new Error('작업 실패');
    if (Date.now() > deadline) throw new Error('시간 초과 (5분)');
    await new Promise(r => setTimeout(r, intervalMs));
  }
}
