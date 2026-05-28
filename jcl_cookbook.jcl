IEFBR14

//CREATE   JOB CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//*
//DD1      DD DSN=TESTE.ARQUIVO,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(1,1)),
//            UNIT=SYSDA,
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=0)
//* NEW     -> cria dataset novo
//* CATLG   -> cataloga se terminar OK
//* DELETE  -> remove se ocorrer erro
//* SPACE   -> espaco alocado
//* DCB     -> caracteristicas do arquivo




//DELETE   JOB CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//*
//DD1      DD DSN=TESTE.ARQUIVO,
//            DISP=(OLD,DELETE,DELETE)
//
//* OLD     -> dataset deve existir
//* DELETE  -> remove ao final
//* 
//* 

IEBGENER

//COPYJOB  JOB CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEBGENER
//*
//SYSPRINT DD SYSOUT=*
//*
//SYSUT1   DD DSN=INPUT.FILE,DISP=SHR
//* SYSUT1 = arquivo de entrada
//* SHR    = acesso compartilhado
//*
//SYSUT2   DD DSN=OUTPUT.FILE,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(1,1)),
//            UNIT=SYSDA,
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=0)
//* SYSUT2 = arquivo de saída
//*
//SYSIN    DD DUMMY
//* Sem comandos adicionais
//* 
//* 
//* 
//* 
//* 
//* 
//STEP1    EXEC PGM=IEBCOPY
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD DSN=INPUT.PDS,DISP=SHR
//SYSUT2   DD DSN=OUTPUT.PDS,DISP=SHR
//SYSIN    DD *
  COPY OUTDD=SYSUT2,INDD=SYSUT1
    SELECT MEMBER=(MEMBRO1,MEMBRO2)
/*



Remove espaço inutilizado de membros deletados.
/*//COMPRESS JOB CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEBCOPY
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD DSN=MINHA.PDS,DISP=OLD
//SYSUT2   DD DSN=MINHA.PDS,DISP=OLD
//SYSIN    DD *
  COPY OUTDD=SYSUT2,INDD=SYSUT1
/


//DELETE   JOB CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IDCAMS
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  DELETE TESTE.VSAM.CLUSTER
/*

