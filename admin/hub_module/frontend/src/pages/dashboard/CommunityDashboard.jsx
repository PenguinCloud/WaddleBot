import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { communityApi, streamApi, adminApi } from '../../services/api';
import LiveStreamGrid from '../../components/streams/LiveStreamGrid';
import LeaderboardCard from '../../components/leaderboard/LeaderboardCard';
import BotScoreBadge from '../../components/BotScoreBadge';
import BotScoreCard from '../../components/BotScoreCard';
import CommunityStatsWidget from '../../components/dashboard/CommunityStatsWidget';
import QuickActionsWidget from '../../components/dashboard/QuickActionsWidget';
import CommunityReputationPanel from '../../components/dashboard/CommunityReputationPanel';
import { MegaphoneIcon, MapPinIcon } from '@heroicons/react/24/outline';

function CommunityDashboard() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [streams, setStreams] = useState([]);
  const [streamsLoading, setStreamsLoading] = useState(false);
  const [streamsError, setStreamsError] = useState(null);
  const [announcements, setAnnouncements] = useState([]);
  const [announcementsLoading, setAnnouncementsLoading] = useState(false);
  const [botScore, setBotScore] = useState(null);

  useEffect(() => {
    async function fetchDashboard() {
      try {
        const response = await communityApi.getDashboard(id);
        setData(response.data);

        // Set initial streams from dashboard data
        if (response.data.liveStreams) {
          setStreams(response.data.liveStreams);
        }
      } catch (err) {
        console.error('Failed to fetch dashboard:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchDashboard();
  }, [id]);

  // Fetch announcements (pinned and recent published)
  useEffect(() => {
    async function fetchAnnouncements() {
      setAnnouncementsLoading(true);
      try {
        const response = await adminApi.getAnnouncements(id, { status: 'published', limit: 5 });
        if (response.data.success) {
          setAnnouncements(response.data.data || []);
        }
      } catch (err) {
        // Silently fail - user may not have access to announcements
        console.error('Failed to fetch announcements:', err);
      } finally {
        setAnnouncementsLoading(false);
      }
    }
    fetchAnnouncements();
  }, [id]);

  // Fetch bot score (for admins)
  useEffect(() => {
    async function fetchBotScore() {
      try {
        const response = await adminApi.getBotScore(id);
        if (response.data.success && response.data.botScore?.isCalculated) {
          setBotScore(response.data.botScore);
        }
      } catch (err) {
        // Silently fail - user may not have admin access
        console.debug('Bot score not available:', err.message);
      }
    }
    fetchBotScore();
  }, [id]);

  const refreshStreams = async () => {
    setStreamsLoading(true);
    setStreamsError(null);
    try {
      const response = await streamApi.getLiveStreams(id);
      if (response.data.success) {
        setStreams(response.data.streams);
      }
    } catch (err) {
      console.error('Failed to refresh streams:', err);
      setStreamsError(err.response?.data?.message || 'Failed to load streams');
    } finally {
      setStreamsLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold-400"></div>
      </div>
    );
  }

  if (!data) {
    return <div className="text-center py-12 text-navy-400">Failed to load dashboard</div>;
  }

  const { community, membership, recentActivity, liveStreams } = data;

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center space-x-4">
          <div className="w-16 h-16 rounded-xl bg-navy-800 flex items-center justify-center overflow-hidden border border-navy-600">
            {community.logoUrl ? (
              <img src={community.logoUrl} alt={community.displayName} className="w-full h-full object-cover" />
            ) : (
              <img src="/waddlebot-logo.png" alt="Community Logo" className="w-12 h-12" />
            )}
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-2xl font-bold text-sky-100">{community.displayName}</h1>
              {botScore && (
                <BotScoreBadge
                  grade={botScore.grade}
                  score={botScore.score}
                  showScore={true}
                  size="md"
                />
              )}
            </div>
            <p className="text-navy-400 capitalize">{membership.role.replace('community-', '').replace('-', ' ')}</p>
          </div>
        </div>
        {['community-owner', 'community-admin', 'moderator'].includes(membership.role) && (
          <Link to={`/admin/${id}`} className="btn btn-primary">
            Admin Panel
          </Link>
        )}
      </div>

      {/* Live Streams Section */}
      {streams && streams.length > 0 && (
        <div className="mb-8">
          <LiveStreamGrid
            streams={streams}
            onRefresh={refreshStreams}
            loading={streamsLoading}
            error={streamsError}
          />
        </div>
      )}

      {/* Announcements Section */}
      {announcements.length > 0 && (
        <div className="mb-8">
          <div className="card">
            <div className="card-header flex items-center justify-between">
              <h2 className="font-semibold text-sky-100 flex items-center space-x-2">
                <MegaphoneIcon className="w-5 h-5 text-gold-400" />
                <span>Announcements</span>
              </h2>
              {['community-owner', 'community-admin', 'moderator'].includes(membership?.role) && (
                <Link
                  to={`/admin/${id}/announcements`}
                  className="text-sm text-sky-400 hover:text-sky-300"
                >
                  Manage
                </Link>
              )}
            </div>
            <div className="divide-y divide-navy-700">
              {announcementsLoading ? (
                <div className="p-4 flex justify-center">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-gold-400"></div>
                </div>
              ) : (
                announcements.slice(0, 3).map((announcement) => (
                  <div
                    key={announcement.id}
                    className={`p-4 ${
                      announcement.announcementType === 'important'
                        ? 'bg-red-500/10 border-l-4 border-l-red-500'
                        : announcement.announcementType === 'event'
                        ? 'bg-purple-500/10 border-l-4 border-l-purple-500'
                        : announcement.announcementType === 'update'
                        ? 'bg-sky-500/10 border-l-4 border-l-sky-500'
                        : ''
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          {announcement.isPinned && (
                            <MapPinIcon className="w-4 h-4 text-gold-400" />
                          )}
                          <h3 className="font-medium text-sky-100">{announcement.title}</h3>
                        </div>
                        <p className="text-sm text-navy-300 mt-1 line-clamp-2">
                          {announcement.content}
                        </p>
                        <div className="flex items-center space-x-2 mt-2 text-xs text-navy-500">
                          <span>{announcement.createdByName || 'Admin'}</span>
                          <span>·</span>
                          <span>{new Date(announcement.createdAt).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <span
                        className={`text-xs px-2 py-1 rounded ${
                          announcement.announcementType === 'important'
                            ? 'bg-red-500/20 text-red-400'
                            : announcement.announcementType === 'event'
                            ? 'bg-purple-500/20 text-purple-400'
                            : announcement.announcementType === 'update'
                            ? 'bg-sky-500/20 text-sky-400'
                            : 'bg-navy-600 text-navy-300'
                        }`}
                      >
                        {announcement.announcementType.charAt(0).toUpperCase() +
                          announcement.announcementType.slice(1)}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Stats cards */}
        <div className="lg:col-span-2 space-y-6">
          <div className="grid sm:grid-cols-3 gap-4">
            <div className="card p-4 border-l-4 border-l-sky-400">
              <div className="text-2xl font-bold text-sky-400">{community.memberCount}</div>
              <div className="text-navy-400 text-sm">Members</div>
            </div>
            <div className="card p-4 border-l-4 border-l-gold-400">
              <div className="text-2xl font-bold text-gold-400">{membership.reputation?.score || 600}</div>
              <div className="text-navy-400 text-sm capitalize">
                {membership.reputation?.label || 'Fair'} Rep
              </div>
            </div>
            <div className="card p-4 border-l-4 border-l-purple-400">
              <div className="text-2xl font-bold text-purple-400">{liveStreams.length}</div>
              <div className="text-navy-400 text-sm">Live Now</div>
            </div>
          </div>

          {/* Recent Activity */}
          <div className="card">
            <div className="card-header">
              <h2 className="font-semibold text-sky-100">Recent Activity</h2>
            </div>
            <div className="divide-y divide-navy-700">
              {recentActivity.length === 0 ? (
                <div className="p-4 text-navy-400 text-center">No recent activity</div>
              ) : (
                recentActivity.slice(0, 5).map((activity) => (
                  <div key={activity.id} className="p-4">
                    <p className="text-sm text-sky-100">{activity.description}</p>
                    <p className="text-xs text-navy-500 mt-1">
                      {new Date(activity.createdAt).toLocaleString()}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Bot Score Card (admin only) */}
          {['community-owner', 'community-admin'].includes(membership?.role) && (
            <BotScoreCard
              communityId={id}
              isPremium={community.isPremium || false}
            />
          )}

          {/* Reputation (gh-310): my score/tier + top-10 community leaderboard */}
          <CommunityReputationPanel communityId={id} />

          {/* Leaderboards */}
          <LeaderboardCard
            communityId={id}
            type="watch-time"
            title="Top Viewers"
            limit={5}
          />
          <LeaderboardCard
            communityId={id}
            type="messages"
            title="Top Chatters"
            limit={5}
          />

          {/* Live Streams */}
          {liveStreams.length > 0 && (
            <div className="card">
              <div className="card-header">
                <h2 className="font-semibold text-sky-100 flex items-center space-x-2">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
                  </span>
                  <span>Live Now</span>
                </h2>
              </div>
              <div className="divide-y divide-navy-700">
                {liveStreams.map((stream) => (
                  <a
                    key={stream.entityId}
                    href={`https://twitch.tv/${stream.channelName}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block p-4 hover:bg-navy-800 transition-colors"
                  >
                    <div className="font-medium text-sky-100">{stream.channelName}</div>
                    <div className="text-sm text-navy-400 truncate">{stream.title}</div>
                    <div className="text-xs text-navy-500 mt-1">
                      {stream.viewerCount.toLocaleString()} viewers
                    </div>
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* Community Stats */}
          <CommunityStatsWidget
            community={data?.community}
            recentActivity={data?.recentActivity}
            streams={streams}
          />

          {/* Quick Actions — curated shortcuts not in sidebar */}
          <QuickActionsWidget id={id} />
        </div>
      </div>
    </div>
  );
}

export default CommunityDashboard;
