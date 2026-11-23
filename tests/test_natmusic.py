"""Unit tests for Nat Music core queue, extractor utilities, and card renderer."""

from __future__ import annotations

import asyncio
import unittest
from PIL import Image

from natmusic.core.queue import LoopMode, QueueManager, Track
from natmusic.ui.cards import format_now_playing_caption, render_now_playing_card_sync


class TestQueueManager(unittest.TestCase):
    def setUp(self) -> None:
        self.qm = QueueManager()
        self.chat_id = -100123456

    def _track(self, idx: int) -> Track:
        return Track(
            title=f"Track {idx}",
            stream_url=f"https://example.com/{idx}.m4a",
            webpage_url=f"https://youtube.com/watch?v={idx}",
            duration_sec=180 + idx,
            duration_str="3:00",
            artist=f"Artist {idx}",
            requester_id=100 + idx,
            requester_name=f"User {idx}",
        )

    def test_enqueue_and_advance(self) -> None:
        async def run() -> None:
            t1, t2, t3 = self._track(1), self._track(2), self._track(3)
            started1, pos1 = await self.qm.enqueue(self.chat_id, t1)
            started2, pos2 = await self.qm.enqueue(self.chat_id, t2)
            started3, pos3 = await self.qm.enqueue(self.chat_id, t3, play_next=True)

            self.assertTrue(started1)
            self.assertEqual(pos1, 0)
            self.assertFalse(started2)
            self.assertEqual(pos2, 1)
            self.assertFalse(started3)
            self.assertEqual(pos3, 1)  # play_next placed t3 at front

            nxt = await self.qm.advance(self.chat_id)
            self.assertIsNotNone(nxt)
            self.assertEqual(nxt.title, "Track 3")

            prev = await self.qm.previous(self.chat_id)
            self.assertIsNotNone(prev)
            self.assertEqual(prev.title, "Track 1")

        asyncio.run(run())

    def test_loop_modes(self) -> None:
        async def run() -> None:
            t1, t2 = self._track(1), self._track(2)
            await self.qm.enqueue(self.chat_id, t1)
            await self.qm.enqueue(self.chat_id, t2)
            state = self.qm.get_state(self.chat_id)

            state.loop_mode = LoopMode.TRACK
            nxt = await self.qm.advance(self.chat_id)
            self.assertEqual(nxt.title, "Track 1")

            state.loop_mode = LoopMode.QUEUE
            nxt2 = await self.qm.advance(self.chat_id, force_skip=True)
            self.assertEqual(nxt2.title, "Track 2")
            self.assertEqual(len(state.upcoming), 1)
            self.assertEqual(state.upcoming[0].title, "Track 1")

        asyncio.run(run())

    def test_remove_move_clear(self) -> None:
        async def run() -> None:
            for i in range(1, 5):
                await self.qm.enqueue(self.chat_id, self._track(i))
            moved = await self.qm.move(self.chat_id, 3, 1)
            self.assertEqual(moved.title, "Track 4")
            removed = await self.qm.remove_at(self.chat_id, 2)
            self.assertEqual(removed.title, "Track 2")
            cleared = await self.qm.clear(self.chat_id, keep_current=True)
            self.assertEqual(cleared, 2)
            self.assertIsNotNone(self.qm.get_state(self.chat_id).current)

        asyncio.run(run())


class TestUIRenderer(unittest.TestCase):
    def test_card_render_and_caption(self) -> None:
        track = Track(
            title="Midnight City (Refined Mix)",
            stream_url="https://example.com/stream.m4a",
            webpage_url="https://youtube.com/watch?v=abc",
            duration_sec=244,
            duration_str="4:04",
            artist="M83",
            requester_id=1,
            requester_name="Nat",
        )
        dummy_art = Image.new("RGB", (600, 600), (45, 75, 160))
        buf = render_now_playing_card_sync(track, art_img=dummy_art, bot_name="Nat Music", eq_preset="studio", volume=110)
        img = Image.open(buf)
        self.assertEqual(img.size, (1280, 720))

        qm = QueueManager()
        state = qm.get_state(1)
        state.current = track
        caption = format_now_playing_caption(state, bot_name="Nat Music")
        self.assertIn("Midnight City", caption)
        self.assertIn("M83", caption)


if __name__ == "__main__":
    unittest.main()
