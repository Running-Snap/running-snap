import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { apiListShortformJobs, ShortformJob } from '@/constants/api';

export default function ShortformListScreen() {
  const [jobs, setJobs] = useState<ShortformJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    apiListShortformJobs()
      .then(data => setJobs(data.filter(j => j.status === 'done')))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}>
          <Text style={styles.backButton}>← 뒤로</Text>
        </TouchableOpacity>
        <Text style={styles.title}>숏폼 기록</Text>
        <Text style={styles.subtitle}>총 {jobs.length}개의 숏폼</Text>
      </View>

      {isLoading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#FF3B30" />
        </View>
      ) : (
        <ScrollView style={styles.content}>
          {jobs.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyIcon}>🎬</Text>
              <Text style={styles.emptyText}>아직 만든 숏폼이 없어요</Text>
              <Text style={styles.emptySubText}>첫 숏폼을 만들어보세요!</Text>
              <TouchableOpacity style={styles.createButton} onPress={() => router.push('/create-shortform')}>
                <Text style={styles.createButtonText}>숏폼 만들러 가기</Text>
              </TouchableOpacity>
            </View>
          ) : (
            jobs.map(job => {
              const videoCount = job.video_ids_json ? (JSON.parse(job.video_ids_json) as number[]).length : 1;
              const date = job.created_at ? new Date(job.created_at).toLocaleDateString('ko-KR') : '';
              return (
                <TouchableOpacity
                  key={job.id}
                  style={styles.shortformCard}
                  onPress={() => router.push({ pathname: '/shortform-result', params: { jobId: String(job.id) } })}
                >
                  <View style={styles.thumbnail}>
                    <Text style={styles.thumbnailIcon}>🎬</Text>
                  </View>
                  <View style={styles.shortformInfo}>
                    <Text style={styles.shortformDate}>{date}</Text>
                    <Text style={styles.shortformDetails}>
                      🎥 영상 {videoCount}개 • 스타일: {job.style}
                    </Text>
                  </View>
                  <Text style={styles.arrowIcon}>›</Text>
                </TouchableOpacity>
              );
            })
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8f9fa' },
  header: {
    paddingTop: 60, paddingHorizontal: 20, paddingBottom: 20,
    backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  backButton: { fontSize: 16, color: '#007AFF', marginBottom: 16 },
  title: { fontSize: 28, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  subtitle: { fontSize: 14, color: '#666' },
  loadingContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  content: { flex: 1, padding: 16 },
  emptyState: { alignItems: 'center', paddingVertical: 60 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyText: { fontSize: 16, fontWeight: 'bold', color: '#666', marginBottom: 4 },
  emptySubText: { fontSize: 14, color: '#aaa', marginBottom: 24 },
  createButton: { backgroundColor: '#FF3B30', borderRadius: 12, paddingVertical: 12, paddingHorizontal: 24 },
  createButtonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  shortformCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12,
    flexDirection: 'row', alignItems: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2,
  },
  thumbnail: {
    width: 60, height: 60, backgroundColor: '#000', borderRadius: 8,
    alignItems: 'center', justifyContent: 'center', marginRight: 16,
  },
  thumbnailIcon: { fontSize: 24 },
  shortformInfo: { flex: 1 },
  shortformDate: { fontSize: 16, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  shortformDetails: { fontSize: 14, color: '#666' },
  arrowIcon: { fontSize: 24, color: '#ccc' },
});
