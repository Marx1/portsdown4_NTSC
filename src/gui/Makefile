all:	rpidatvtouch4

clean:
	rm -f *.o *.inc *.so *.c~ *.h~
	indent -linux -c 60 -brf -l 132

INCLUDEFLAGS2=-I..
LIBFLAGS2=-lpthread -ljpeg -lrt -lm -ldl -lfftw3f -lwiringPi -lLimeSuite -lfcgi -rdynamic

rpidatvtouch4: rpidatvtouch4.c 
	gcc -Wall $(INCLUDEFLAGS2) -o  rpidatvgui \
		font/font.c \
		font/dejavu_sans_18.c \
		font/dejavu_sans_20.c \
		font/dejavu_sans_22.c \
		font/dejavu_sans_24.c \
		font/dejavu_sans_26.c \
		font/dejavu_sans_28.c \
		font/dejavu_sans_30.c \
		font/dejavu_sans_32.c \
		font/dejavu_sans_72.c \
		timing.c \
		lmrx_utils.c \
		ffunc.c \
		ffunc.h \
		rpidatvtouch4.c $(LIBFLAGS2) 

install:
	cp rpidatvgui ../../bin/
