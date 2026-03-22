import { useLocalSearchParams, router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator, ScrollView,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useVideoPlayer, VideoView } from 'expo-video';
import { useEvent } from 'expo';
import { apiGetShortformJob, API_BASE } from '@/constants/api';

const STYLE_LABELS: Record<string, string> = {
  action: '스포츠 액션샷',
  instagram: '인스타그램',
  tiktok: '틱톡',
  humor: '밈/유머',
  documentary: '다큐',
};

export default function ShortformResultScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>();
  const [outputFilename, setOutputFilename] = useState<string | null>(null);
  const [createdAt, setCreatedAt] = useState('');
  const [style, setStyle] = useState('');
  const [durationSec, setDurationSec] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [actualDuration, setActualDuration] = useState<number | null>(null);

  useEffect(() => {
    if (!jobId) return;
    apiGetShortformJob(Number(jobId))
      .then(job => {
        setOutputFilename(job.output_filename);
        setStyle(job.style);
        setDurationSec(job.duration_sec);
        setCreatedAt(job.created_at ? new Date(job.created_at).toLocaleDateString('ko-KR') : '');
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [jobId]);

  const videoUrl = outputFilename
    ? `${API_BASE}/outputs/videos/${outputFilename}`
    : null;

  const player = useVideoPlayer(videoUrl ?? '');
  useEvent(player, 'statusChange', () => {
    if (player.duration > 0) setActualDuration(Math.round(player.duration));
  });

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#FF3B30" />
        <Text style={styles.loadingText}>결과 불러오는 중...</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}>
          <Text style={styles.backButton}>← 뒤로</Text>
        </TouchableOpacity>
        <Text style={styles.title}>숏폼 완성!</Text>
      </View>

      <View style={styles.successCard}>
        <Text style={styles.successIcon}>🎉</Text>
        <Text style={styles.successTitle}>숏폼이 완성되었어요!</Text>
        <Text style={styles.successSubtitle}>
          AI가 당신의 러닝 하이라이트를 멋지게 편집했어요
        </Text>
      </View>

      {videoUrl && (
        <View style={styles.videoContainer}>
          <VideoView player={player} style={styles.videoPlayer} contentFit="contain" nativeControls />
        </View>
      )}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>영상 정보</Text>
        <View style={styles.infoCard}>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>스타일</Text>
            <Text style={styles.infoValue}>{STYLE_LABELS[style] ?? style}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>영상 길이</Text>
            <Text style={styles.infoValue}>{actualDuration != null ? `${actualDuration}초` : `${durationSec}초`}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>생성 날짜</Text>
            <Text style={styles.infoValue}>{createdAt}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>파일</Text>
            <Text style={styles.infoValue} numberOfLines={1}>
              {outputFilename ?? '생성 중...'}
            </Text>
          </View>
        </View>
      </View>

      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.homeButton} onPress={() => router.replace('/(tabs)')}>
          <Text style={styles.homeButtonText}>홈으로 돌아가기</Text>
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
  successCard: {
    backgroundColor: '#fff', margin: 16, padding: 32, borderRadius: 16,
    alignItems: 'center', shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 8, elevation: 3,
  },
  successIcon: { fontSize: 64, marginBottom: 16 },
  successTitle: { fontSize: 24, fontWeight: 'bold', color: '#000', marginBottom: 8 },
  successSubtitle: { fontSize: 14, color: '#666', textAlign: 'center', lineHeight: 20 },
  videoContainer: {
    marginHorizontal: 16, marginBottom: 8,
    borderRadius: 12, overflow: 'hidden',
    backgroundColor: '#000', height: 240,
  },
  videoPlayer: { width: '100%', height: '100%' },
  section: { padding: 16 },
  sectionTitle: { fontSize: 18, fontWeight: 'bold', color: '#000', marginBottom: 12 },
  infoCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16 },
  infoRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  infoLabel: { fontSize: 16, color: '#666' },
  infoValue: { fontSize: 14, fontWeight: 'bold', color: '#000', flex: 1, textAlign: 'right', marginLeft: 12 },
  buttonContainer: { padding: 16, gap: 12, marginBottom: 32 },
  homeButton: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16,
    alignItems: 'center', borderWidth: 1, borderColor: '#ddd',
  },
  homeButtonText: { color: '#666', fontSize: 16, fontWeight: '600' },
});
