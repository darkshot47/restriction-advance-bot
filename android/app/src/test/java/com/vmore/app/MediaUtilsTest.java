package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/** The file-kind rules behind the viewer, the thumbnail tools and the upload. */
public class MediaUtilsTest {

    @Test
    public void extensionsAreReadCaseInsensitively() {
        assertEquals("mp4", MediaUtils.extension("Clip.MP4"));
        assertEquals("", MediaUtils.extension("noextension"));
        assertEquals("", MediaUtils.extension(null));
    }

    @Test
    public void mimeTypesCoverTheFormatsTheBotSends() {
        assertEquals("video/mp4", MediaUtils.mimeOf(new java.io.File("a.mp4")));
        assertEquals("image/jpeg", MediaUtils.mimeOf(new java.io.File("a.JPEG")));
        assertEquals("audio/mpeg", MediaUtils.mimeOf(new java.io.File("song.mp3")));
        assertEquals("application/pdf", MediaUtils.mimeOf(new java.io.File("doc.pdf")));
        assertEquals("application/vnd.android.package-archive",
                MediaUtils.mimeOf(new java.io.File("Vmore.apk")));
        assertEquals("application/octet-stream", MediaUtils.mimeOf(new java.io.File("blob")));
    }

    @Test
    public void kindPredicatesDecideTheViewerAndTheUploadField() {
        assertTrue(MediaUtils.isVideo(new java.io.File("clip.mkv")));
        assertTrue(MediaUtils.isImage(new java.io.File("shot.png")));
        assertTrue(MediaUtils.isPdf(new java.io.File("doc.pdf")));
        assertTrue(MediaUtils.isText(new java.io.File("notes.txt")));
        assertFalse(MediaUtils.isVideo(new java.io.File("shot.png")));
    }

    @Test
    public void onlyMp4FamilyFilesCanBeTrimmedWithoutReEncoding() {
        assertTrue(MediaUtils.canTrim(new java.io.File("clip.mp4")));
        assertTrue(MediaUtils.canTrim(new java.io.File("clip.MOV")));
        assertFalse(MediaUtils.canTrim(new java.io.File("clip.mkv")));
        assertFalse(MediaUtils.canTrim(new java.io.File("clip.webm")));
    }
}
