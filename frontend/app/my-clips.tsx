import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View, RefreshControl } from 'react-native';
import { useVideoPlayer, VideoView } from 'expo-video';
import { router } from 'expo-router';
import { API_BASE, getToken, formatKoreanDateTime } from '@/constants/api';

type ClipMatch = {
  match_id: number;
  clip_id: number;
  trimmed_url: string | null;
  enter_time: string | null;
  exit_time: string | null;
  created_at: string;
};

function ClipCard({ clip, formatTime }: { clip: ClipMatch; formatTime: (s: string | null) => string }) {
  const player = useVideoPlayer(clip.trimmed_url ? (clip.trimmed_url.startsWith('http') ? clip.trimmed_url : `${API_BASE}${clip.trimmed_url}`) : '', p => { p.loop = false; });
  return (
    <View style={styles.card}>
      <Text style={styles.cardDate}>{formatTime(clip.created_at)}</Text>
      <Text style={styles.cardSub}>
        통과 시각: {formatTime(clip.enter_time)} ~ {formatTime(clip.exit_time)}
      </Text>
      {clip.trimmed_url ? (
        <VideoView player={player} style={styles.video} contentFit="contain" nativeControls />
      ) : (
        <View style={styles.noVideo}>
          <Text style={styles.noVideoText}>영상 처리 중...</Text>
        </View>
      )}
    </View>
  );
}

export default function MyClipsScreen() {
  const [clips, setClips] = useState<ClipMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchClips = async () => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/my-clips`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setClips(await res.json());
    } catch {}
    setLoading(false);
    setRefreshing(false);
  };

  useEffect(() => { fetchClips(); }, []);

  const onRefresh = () => { setRefreshing(true); fetchClips(); };

  const formatTime = (iso: string | null) => formatKoreanDateTime(iso);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.back}>← 뒤로</Text>
        </TouchableOpacity>
        <Text style={styles.title}>내 영상</Text>
      </View>

      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {loading && <Text style={styles.empty}>불러오는 중...</Text>}
        {!loading && clips.length === 0 && (
          <Text style={styles.empty}>아직 매칭된 영상이 없습니다.{'\n'}카메라 근처를 지나면 자동으로 영상이 쌓입니다.</Text>
        )}
        {clips.map((clip) => (
          <ClipCard key={clip.match_id} clip={clip} formatTime={formatTime} />
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8f9fa' },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 16,
    padding: 16, paddingTop: 60, backgroundColor: '#fff',
    borderBottomWidth: 1, borderBottomColor: '#eee',
  },
  back: { fontSize: 16, color: '#007AFF' },
  title: { fontSize: 20, fontWeight: 'bold' },
  empty: { textAlign: 'center', color: '#999', marginTop: 60, fontSize: 15, lineHeight: 24 },
  card: {
    backgroundColor: '#fff', margin: 16, borderRadius: 12,
    padding: 16, shadowColor: '#000', shadowOpacity: 0.05,
    shadowRadius: 4, elevation: 2,
  },
  cardDate: { fontSize: 14, fontWeight: 'bold', color: '#333', marginBottom: 4 },
  cardSub: { fontSize: 12, color: '#999', marginBottom: 12 },
  video: { width: '100%', height: 200, borderRadius: 8, backgroundColor: '#000' },
  noVideo: {
    width: '100%', height: 100, borderRadius: 8,
    backgroundColor: '#f0f0f0', alignItems: 'center', justifyContent: 'center',
  },
  noVideoText: { color: '#999' },
});
