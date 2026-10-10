// This effect Copyright (C) 2017 by Ernie 'lunker' Lundqvist
// License: GPL - http://www.gnu.org/licenses/gpl.html

desc: MIDI Filter (Exclude "Note Off" Events)

// Allows all MIDI events to pass through except "note-off" events.

in_pin:none
out_pin:none

slider1:1<0,1,1{Pass Through, Filter Out}>Note Off Events
slider2:1<0,1,1{Pass Through, Filter Out}>Note On (Vel=0)

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

@init

    NOTEON  = 0x90;
    NOTEOFF = 0x80;

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

@block

    while (midirecv (offset, msg1, msg2, msg3)) (

        filter_note_off =  (((msg1 & 0xF0) == NOTEOFF)                && (slider1 == 1));
        filter_note_on0 = ((((msg1 & 0xF0) == NOTEON) && (msg3 == 0)) && (slider2 == 1));

        ((filter_note_off == 0) && (filter_note_on0 == 0)) ? (midisend (offset, msg1, msg2, msg3));

    );

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
