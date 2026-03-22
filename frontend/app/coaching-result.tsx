import { useLocalSearchParams, router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Linking, Platform, ScrollView,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { Video, ResizeMode } from 'expo-av';
import { apiGetCoachingJob, API_BASE } from '@/constants/api';

export default function CoachingResultScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>();
  const [outputFilename, setOutputFilename] = useState<string | null>(null);
  const [coachingText, setCoachingText] = useState<string | null>(null);
  const [createdAt, setCreatedAt] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [videoError, setVideoError] = useState(false);
  const videoRef = useRef<Video>(null);

  useEffect(() => {
    if (!jobId) return;
    apiGetCoachingJob(Number(jobId))
      .then(job => {
        setOutputFilename(job.output_filename);
        setCoachingText(job.coaching_text);
        setCreatedAt(
          job.created_at ? new Date(job.created_at).toLocaleDateString('ko-KR') : ''
        );
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [jobId]);

  const videoUrl = outputFilename
    ? `${API_BASE}/outputs/coaching/${outputFilename}`
    : null;

  const openInBrowser = () => {
    if (videoUrl) Linking.openURL(videoUrl);
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#5856D6" />
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
        <Text style={styles.title}>코칭 영상 완성!</Text>
      </View>

      {/* 완성 카드 */}
      <View style={styles.successCard}>
        <Text style={styles.successIcon}>🎬</Text>
        <Text style={styles.successTitle}>코칭 영상이 완성되었어요!</Text>
        <Text style={styles.successSubtitle}>
          AI 코칭 내용이 담긴 러닝 영상을 확인해보세요
        </Text>
      </View>

      {/* 앱 내 영상 플레이어 */}
      {videoUrl && !videoError && (
        <View style={styles.videoContainer}>
          {Platform.OS === 'web' ? (
            <video
              src={videoUrl}
              controls
              style={{ width: '100%', height: '100%', borderRadius: 12, backgroundColor: '#000' }}
              onError={() => setVideoError(true)}
            />
          ) : (
            <Video
              ref={videoRef}
              source={{ uri: videoUrl }}
              style={styles.videoPlayer}
              useNativeControls
              resizeMode={ResizeMode.CONTAIN}
              shouldPlay={false}
              onError={() => setVideoError(true)}
            />
          )}
        </View>
      )}

      {/* 영상 재생 오류 시 대체 UI */}
      {videoUrl && videoError && (
        <View style={styles.videoErrorContainer}>
          <Text style={styles.videoErrorIcon}>⚠️</Text>
          <Text style={styles.videoErrorText}>앱 내 재생을 지원하지 않는 환경입니다</Text>
          <Text style={styles.videoErrorSubText}>아래 버튼으로 브라우저에서 재생하세요</Text>
        </View>
      )}

      {/* 브라우저에서 열기 버튼 */}
      {videoUrl && (
        <View style={{ paddingHorizontal: 16, marginBottom: 8 }}>
          <TouchableOpacity style={styles.openButton} onPress={openInBrowser}>
            <Text style={styles.openButtonText}>🔗 브라우저에서 영상 열기</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* 영상 정보 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>영상 정보</Text>
        <View style={styles.infoCard}>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>생성 날짜</Text>
            <Text style={styles.infoValue}>{createdAt}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>파일명</Text>
            <Text style={styles.infoValue} numberOfLines={1}>
              {outputFilename ?? '생성 실패'}
            </Text>
          </View>
        </View>
      </View>

      {/* 코칭 내용 */}
      {coachingText && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📋 코칭 내용</Text>
          <View style={styles.coachingCard}>
            <Text style={styles.coachingText}>{coachingText}</Text>
          </View>
        </View>
      )}

      {/* 버튼 */}
      <View style={styles.buttonContainer}>
        {!outputFilename && (
          <View style={styles.failCard}>
            <Text style={styles.failText}>영상 생성에 실패했습니다.</Text>
            <Text style={styles.failSubText}>영상 파일을 다시 확인해주세요.</Text>
          </View>
        )}
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
  videoErrorContainer: {
    marginHorizontal: 16, marginBottom: 8,
    backgroundColor: '#FFF8E1', borderRadius: 12, padding: 24,
    alignItems: 'center', borderWidth: 1, borderColor: '#FFB300',
  },
  videoErrorIcon: { fontSize: 40, marginBottom: 8 },
  videoErrorText: { fontSize: 15, fontWeight: '600', color: '#E65100', marginBottom: 4 },
  videoErrorSubText: { fontSize: 13, color: '#666', textAlign: 'center' },
  openButton: {
    backgroundColor: '#5856D6', borderRadius: 12, padding: 14,
    alignItems: 'center',
  },
  openButtonText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  section: { padding: 16 },
  sectionTitle: { fontSize: 18, fontWeight: 'bold', color: '#000', marginBottom: 12 },
  infoCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16 },
  infoRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  infoLabel: { fontSize: 16, color: '#666' },
  infoValue: { fontSize: 14, fontWeight: 'bold', color: '#000', flex: 1, textAlign: 'right', marginLeft: 12 },
  coachingCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 20,
    borderLeftWidth: 4, borderLeftColor: '#5856D6',
  },
  coachingText: { fontSize: 14, color: '#333', lineHeight: 22 },
  buttonContainer: { padding: 16, gap: 12, marginBottom: 32 },
  homeButton: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16,
    alignItems: 'center', borderWidth: 1, borderColor: '#ddd',
  },
  homeButtonText: { color: '#666', fontSize: 16, fontWeight: '600' },
  failCard: {
    backgroundColor: '#FFF5F5', borderRadius: 12, padding: 20,
    alignItems: 'center', borderWidth: 1, borderColor: '#FF3B30',
  },
  failText: { fontSize: 16, fontWeight: 'bold', color: '#FF3B30', marginBottom: 4 },
  failSubText: { fontSize: 14, color: '#666' },
});
