#include "std_testcase.h"
void case_sink(int * data)
{
    {
        int source[10] = {0};
        size_t i;
        for (i = 0; i < 10; i++)
        {
            data[i] = source[i];
        }
        printIntLine(data[0]);
        free(data);
    }
}
void case_entry()
{
    int * data;
    data = NULL;
    data = (int *)malloc(10*sizeof(int));
    if (data == NULL) {exit(-1);}
    case_sink(data);
}
