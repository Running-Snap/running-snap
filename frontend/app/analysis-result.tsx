import { useLocalSearchParams, router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator, ScrollView, StyleSheet, Text,
  TouchableOpacity, View, Alert,
} from 'react-native';
import {
  apiGetAnalysisJob, apiCreateCoachingJob, apiGetCoachingJob,
  pollUntilDone, PoseStats,
} from '@/constants/api';

type Feedback = { title: string; status: string; message: string };
type AnalysisResult = {
  score: number;
  feedbacks: Feedback[];
  pose_stats?: PoseStats;
  coaching_report?: string;
};

export default function AnalysisResultScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [videoId, setVideoId] = useState<number | null>(null);
  const [createdAt, setCreatedAt] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isCreatingCoaching, setIsCreatingCoaching] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    apiGetAnalysisJob(Number(jobId))
      .then(job => {
        if (job.result_json) {
          setResult(JSON.parse(job.result_json) as AnalysisResult);
        }
        setVideoId(job.video_id);
        setCreatedAt(job.created_at ? new Date(job.created_at).toLocaleDateString('ko-KR') : '');
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [jobId]);

  const getScoreColor = (score: number) => {
    if (score >= 80) return '#34C759';
    if (score >= 60) return '#FF9500';
    return '#FF3B30';
  };

  const getStatusIcon = (s: string) => s === 'good' ? '✅' : s === 'warning' ? '⚠️' : '❌';
  const getStatusColor = (s: string) => s === 'good' ? '#34C759' : s === 'warning' ? '#FF9500' : '#FF3B30';

  const handleCreateCoaching = async () => {
    if (!videoId || !result) return;

    setIsCreatingCoaching(true);
    try {
      const coachingText = result.coaching_report
        || result.feedbacks.map(fb => fb.message).join(' ')
        || '좋은 자세를 유지하며 달리세요.';

      const job = await apiCreateCoachingJob(
        videoId,
        coachingText,
        Number(jobId),
      );

      const doneJob = await pollUntilDone(() => apiGetCoachingJob(job.id));

      router.push({
        pathname: '/coaching-result',
        params: { jobId: String(doneJob.id) },
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '코칭 영상 생성 실패';
      Alert.alert('오류', msg);
    } finally {
      setIsCreatingCoaching(false);
    }
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#007AFF" />
        <Text style={styles.loadingText}>결과 불러오는 중...</Text>
      </View>
    );
  }

  if (!result) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>결과를 불러올 수 없습니다.</Text>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}>
          <Text style={{ color: '#007AFF', marginTop: 16 }}>뒤로 가기</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const ps = result.pose_stats;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}>
          <Text style={styles.backButton}>← 뒤로</Text>
        </TouchableOpacity>
        <Text style={styles.title}>분석 결과</Text>
      </View>

      {/* 점수 카드 */}
      <View style={styles.scoreCard}>
        <Text style={styles.scoreLabel}>자세 점수</Text>
        <Text style={[styles.scoreValue, { color: getScoreColor(result.score) }]}>
          {result.score}점
        </Text>
        <View style={styles.scoreBar}>
          <View
            style={[
              styles.scoreBarFill,
              { width: `${result.score}%` as `${number}%`, backgroundColor: getScoreColor(result.score) },
            ]}
          />
        </View>
        {createdAt ? (
          <View style={styles.scoreInfo}>
            <Text style={styles.scoreInfoText}>📅 {createdAt}</Text>
          </View>
        ) : null}
      </View>

      {/* 바이오메카닉스 통계 */}
      {ps && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>러닝 바이오메카닉스</Text>
          <View style={styles.statsGrid}>
            <View style={styles.statCard}>
              <Text style={styles.statValue}>{ps.cadence}</Text>
              <Text style={styles.statUnit}>spm</Text>
              <Text style={styles.statLabel}>케이던스</Text>
              <Text style={[styles.statBadge, { color: ps.cadence >= 160 && ps.cadence <= 185 ? '#34C759' : '#FF9500' }]}>
                {ps.cadence >= 160 && ps.cadence <= 185 ? '이상적' : '개선 필요'}
              </Text>
            </View>
            <View style={styles.statCard}>
              <Text style={styles.statValue}>{ps.v_oscillation.toFixed(1)}</Text>
              <Text style={styles.statUnit}>cm</Text>
              <Text style={styles.statLabel}>수직 진동</Text>
              <Text style={[styles.statBadge, { color: ps.v_oscillation <= 8 ? '#34C759' : '#FF9500' }]}>
                {ps.v_oscillation <= 8 ? '양호' : '높음'}
              </Text>
            </View>
            <View style={styles.statCard}>
              <Text style={styles.statValue}>{ps.avg_impact_z.toFixed(2)}</Text>
              <Text style={styles.statUnit}>z</Text>
              <Text style={styles.statLabel}>착지 지점</Text>
              <Text style={[styles.statBadge, {
                color: ps.avg_impact_z <= 0.18 ? '#34C759' : ps.avg_impact_z <= 0.4 ? '#FF9500' : '#FF3B30'
              }]}>
                {ps.avg_impact_z <= 0.18 ? '엘리트' : ps.avg_impact_z <= 0.4 ? '양호' : '오버스트라이드'}
              </Text>
            </View>
            <View style={styles.statCard}>
              <Text style={styles.statValue}>{ps.asymmetry.toFixed(1)}</Text>
              <Text style={styles.statUnit}>%</Text>
              <Text style={styles.statLabel}>좌우 비대칭</Text>
              <Text style={[styles.statBadge, { color: ps.asymmetry < 2 ? '#34C759' : '#FF9500' }]}>
                {ps.asymmetry < 2 ? '균형' : '불균형'}
              </Text>
            </View>
            <View style={[styles.statCard, { width: '48%' }]}>
              <Text style={styles.statValue}>{ps.elbow_angle.toFixed(0)}</Text>
              <Text style={styles.statUnit}>°</Text>
              <Text style={styles.statLabel}>팔꿈치 각도</Text>
              <Text style={[styles.statBadge, {
                color: ps.elbow_angle >= 80 && ps.elbow_angle <= 100 ? '#34C759' : '#FF9500'
              }]}>
                {ps.elbow_angle >= 80 && ps.elbow_angle <= 100 ? '이상적' : '조정 필요'}
              </Text>
            </View>
          </View>
        </View>
      )}

      {/* 피드백 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>상세 피드백</Text>
        {result.feedbacks.map((fb, i) => (
          <View key={i} style={styles.feedbackCard}>
            <View style={styles.feedbackHeader}>
              <Text style={styles.feedbackIcon}>{getStatusIcon(fb.status)}</Text>
              <Text style={styles.feedbackTitle}>{fb.title}</Text>
            </View>
            <Text style={[styles.feedbackMessage, { color: getStatusColor(fb.status) }]}>
              {fb.message}
            </Text>
          </View>
        ))}
      </View>

      {/* AI 코칭 리포트 */}
      {result.coaching_report && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>🤖 AI 코칭 리포트</Text>
          <View style={styles.coachingCard}>
            <Text style={styles.coachingText}>{result.coaching_report}</Text>
          </View>
        </View>
      )}

      {/* 버튼 */}
      <View style={styles.buttonContainer}>
        {/* 코칭 영상 만들기 버튼 */}
        {videoId && (
          <TouchableOpacity
            style={[styles.coachingButton, isCreatingCoaching && styles.buttonDisabled]}
            onPress={handleCreateCoaching}
            disabled={isCreatingCoaching}
          >
            {isCreatingCoaching ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={styles.coachingButtonText}>🎬 코칭 영상 만들기</Text>
            )}
          </TouchableOpacity>
        )}
        <TouchableOpacity style={styles.primaryButton} onPress={() => router.replace('/(tabs)')}>
          <Text style={styles.primaryButtonText}>홈으로 돌아가기</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.secondaryButton} onPress={() => router.canGoBack() ? router.back() : router.push('/analyze-video')}>
          <Text style={styles.secondaryButtonText}>다시 분석하기</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8f9fa' },
  loadingContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  loadingText: { fontSize: 16, color: '#666', marginTop: 12 },
  header: {
    paddingTop: 60, paddingHorizontal: 20, paddingBottom: 20,
    backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  backButton: { fontSize: 16, color: '#007AFF', marginBottom: 16 },
  title: { fontSize: 28, fontWeight: 'bold', color: '#000' },
  scoreCard: {
    backgroundColor: '#fff', margin: 16, padding: 24, borderRadius: 16,
    alignItems: 'center', shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 8, elevation: 3,
  },
  scoreLabel: { fontSize: 16, color: '#666', marginBottom: 8 },
  scoreValue: { fontSize: 56, fontWeight: 'bold', marginBottom: 16 },
  scoreBar: {
    width: '100%', height: 8, backgroundColor: '#e9ecef',
    borderRadius: 4, overflow: 'hidden', marginBottom: 16,
  },
  scoreBarFill: { height: '100%', borderRadius: 4 },
  scoreInfo: { flexDirection: 'row', gap: 20 },
  scoreInfoText: { fontSize: 14, color: '#666' },
  section: { padding: 16 },
  sectionTitle: { fontSize: 20, fontWeight: 'bold', color: '#000', marginBottom: 16 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  statCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14,
    width: '47%', alignItems: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2,
  },
  statValue: { fontSize: 24, fontWeight: 'bold', color: '#000' },
  statUnit: { fontSize: 12, color: '#666', marginBottom: 4 },
  statLabel: { fontSize: 12, color: '#666', marginBottom: 4 },
  statBadge: { fontSize: 11, fontWeight: 'bold' },
  feedbackCard: { backgroundColor: '#fff', padding: 16, borderRadius: 12, marginBottom: 12 },
  feedbackHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  feedbackIcon: { fontSize: 20, marginRight: 8 },
  feedbackTitle: { fontSize: 16, fontWeight: 'bold', color: '#000' },
  feedbackMessage: { fontSize: 14, lineHeight: 20 },
  coachingCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 20,
    borderLeftWidth: 4, borderLeftColor: '#007AFF',
  },
  coachingText: { fontSize: 14, color: '#333', lineHeight: 22 },
  buttonContainer: { padding: 16, gap: 12, marginBottom: 32 },
  coachingButton: {
    backgroundColor: '#5856D6', borderRadius: 12, padding: 16,
    alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
  },
  coachingButtonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  buttonDisabled: { backgroundColor: '#ccc' },
  primaryButton: { backgroundColor: '#007AFF', borderRadius: 12, padding: 16, alignItems: 'center' },
  primaryButtonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  secondaryButton: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16,
    alignItems: 'center', borderWidth: 2, borderColor: '#007AFF',
  },
  secondaryButtonText: { color: '#007AFF', fontSize: 16, fontWeight: 'bold' },
});
